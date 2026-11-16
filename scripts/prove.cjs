const fs = require('node:fs');
const {assert, equal, digest, sourceHash, invoke, read, rpc, receipt, receiptSummary, save, delay} = require('./transport.cjs');
const {decodeReceipt} = require('./receipt-calldata.cjs');

const source = 'https://earthquake.usgs.gov/fdsnws/event/1/query';
const days = ['2019-07-03', '2019-07-04', '2019-07-05'];
const config = {start: days[0], west: -119, east: -116, south: 34, north: 37, allowance: 2, trigger: 2, clear: 0};
const argument = 'sd1:' + JSON.stringify(config);
const tomorrow = day => new Date(Date.parse(day) + 86400000).toISOString().slice(0, 10);
const ordered = entries => Object.fromEntries(Object.entries(entries).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));

async function observe(day) {
  const query = new URLSearchParams({format: 'geojson', starttime: day, endtime: tomorrow(day),
    minlatitude: config.south, maxlatitude: config.north, minlongitude: config.west, maxlongitude: config.east,
    minmagnitude: 4.5, limit: 65, orderby: 'time-asc', eventtype: 'earthquake'});
  const url = source + '?' + query;
  let data;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(url, {signal: AbortSignal.timeout(25000)});
      assert(response.ok, 'USGS HTTP ' + response.status);
      data = await response.json();
      break;
    } catch (error) {
      if (attempt === 2) throw error;
      await delay(3000);
    }
  }
  assert(data.metadata.url === url && data.metadata.limit === 65 && data.metadata.offset === 1, 'Unexpected USGS query');
  const events = data.features.filter(event => event.properties.time < Date.parse(tomorrow(day))).map(event => {
    const [longitude, latitude] = event.geometry.coordinates;
    const {mag, time, type} = event.properties;
    assert(type === 'earthquake' && Date.parse(day) <= time && mag >= 4.5
      && longitude >= config.west && longitude <= config.east
      && latitude >= config.south && latitude <= config.north, 'Unexpected USGS event');
    const scale = number => Math.round(number * 1e7);
    return ordered({id: event.id, time_ms: time, longitude_e7: scale(longitude),
      latitude_e7: scale(latitude), magnitude_e7: scale(mag)});
  }).sort((a, b) => a.time_ms - b.time_ms || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)).slice(0, 64);
  assert(new Set(events.map(event => event.id)).size === events.length, 'Duplicate USGS event');
  return {url, events};
}

async function main() {
  const wallets = JSON.parse(process.env.SEISMO_ACCOUNTS || '[]');
  assert(wallets.length === 2 && wallets[0].address !== wallets[1].address, 'Two distinct wallets required');
  const refs = new Map(await Promise.all(days.map(async day => [day, await observe(day)])));
  assert(equal(days.map(day => refs.get(day).events.length), [0, 4, 1]), 'USGS revised the intended historical scenario');
  assert(await rpc('eth_chainId', []) === '0xf22f', 'StudioNet only');
  const code = fs.readFileSync('contracts/seismo_drift.py');
  process.env.SEISMO_ACCOUNT = wallets[0].name;
  const deployment = await invoke('deploy', ['deploy', '--contract', 'contracts/seismo_drift.py', '--args', argument]);
  const deployed = await receipt('deploy', deployment, true);
  const contract = deployed.to_address || deployed.recipient;
  assert(/^0x[0-9a-f]{40}$/i.test(contract) && code.equals(Buffer.from(deployed.data.contract_code, 'base64')), 'Deployed code mismatch');
  const report = {contract, deployment, revision: process.env.GITHUB_SHA, source_sha256: sourceHash, trace: [], days: {}};
  let expected = {config, next_day: days[0], score: 0, active: false};
  const increments = [];

  async function verify(label, raw, actor, args, error) {
    assert((raw.from_address || raw.sender).toLowerCase() === wallets[actor].address
      && (raw.to_address || raw.recipient).toLowerCase() === contract.toLowerCase(), 'Wrong receipt addresses');
    assert(equal(await decodeReceipt(raw), args), 'Unexpected signed calldata');
    if (error) {
      const data = Buffer.from(raw.consensus_data.leader_receipt[0].result, 'base64');
      assert(data[0] === 1 && data.subarray(1).toString() === error, 'Wrong expected error');
    }
    const state = await read(label + '-state', ['call', contract, 'get_state']);
    if (!equal(state, expected)) save('state-mismatch', {label, state, expected});
    assert(equal(state, expected), 'Unexpected monitor state at ' + label);
    report.trace.push({label, ...receiptSummary(raw), signer: wallets[actor].address, args, error: error || null, state});
    save('progress', report);
  }

  async function advance(label, day, actor, error) {
    process.env.SEISMO_ACCOUNT = wallets[actor].name;
    const tx = await invoke(label, ['write', contract, 'advance', '--args', day]);
    const raw = await receipt(label, tx, !error);
    if (!error) {
      const {url, events} = refs.get(day);
      const count = events.length;
      increments.push(count - config.allowance);
      // The running CUSUM equals the maximum suffix sum, including the empty suffix.
      const score = Math.max(0, ...increments.map((_, i) => increments.slice(i).reduce((a, b) => a + b, 0)));
      const active = expected.active ? score > config.clear : score >= config.trigger;
      const transition = active === expected.active ? 'HOLD' : active ? 'OPEN' : 'CLEAR';
      report.days[day] = {day, source: url, events, observation_sha256: digest(JSON.stringify(events)),
        count, at_cap: count === 64, score_before: expected.score, score, active_before: expected.active, active, transition};
      expected = {config, next_day: tomorrow(day), score, active};
    }
    await verify(label, raw, actor, {method: 'advance', args: [day]}, error);
    const record = await read(label + '-day', ['call', contract, 'get_day', '--args', day]);
    if (!equal(record, report.days[day] || {})) save('history-mismatch', {label, record, expected: report.days[day] || {}});
    assert(equal(record, report.days[day] || {}), 'Historical evidence mismatch');
  }

  await verify('deploy', deployed, 0, {args: [argument]});
  await advance('reject-skip', days[1], 1, 'Expected the next unsealed day');
  await advance('quiet', days[0], 1);
  await advance('open', days[1], 0);
  await advance('hold', days[2], 1);
  await advance('reject-replay', days[1], 0, 'Expected the next unsealed day');
  assert(code.equals(Buffer.from(await rpc('gen_getContractCode', [contract]), 'base64')), 'Fresh code differs');
  save('verified', report);
  console.log(JSON.stringify({contract, deployment, receipts: report.trace.length,
    days: Object.values(report.days).map(({day,count,score,transition}) => ({day,count,score,transition}))}));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
