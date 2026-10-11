// Independently shipped finance client. All requests go through HTTP.
const ABI = 1;
const args = process.argv.slice(2);
if (args[0] === 'version') { console.log(JSON.stringify({release_abi: ABI})); }
else {
  const [base, token, command, ...rest] = args;
  async function request(path, body) {
    const response = await fetch(base + path, {method: body === undefined ? 'GET' : 'POST', headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
    const text = await response.text();
    if (!response.ok) throw new Error(text);
    return response.headers.get('content-type').includes('application/json') ? JSON.parse(text) : text;
  }
  try {
    let result;
    if (command === 'list') {
      result = {returns: []}; let cursor = null;
      do {
        const query = new URLSearchParams({order_id: rest[0], limit: rest[1] || '2'});
        if (cursor) query.set('cursor', cursor);
        const page = await request('/v3/returns?' + query);
        result.returns.push(...page.returns); cursor = page.next_cursor;
      } while (cursor);
    } else if (command === 'settle') result = await request('/v2/returns/' + encodeURIComponent(rest[0]) + '/settle', {});
    else if (command === 'get') result = await request('/v3/payouts/' + encodeURIComponent(rest[0]));
    else if (command === 'export') result = await request('/v2/refunds.csv');
    else throw new Error('unknown command');
    process.stdout.write(typeof result === 'string' ? result : JSON.stringify(result));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
