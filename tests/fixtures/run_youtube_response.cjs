/* Offline regression harness. The VM has no file/network/process/require APIs. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[2], "utf8");

function varint(value) {
  const result = [];
  do {
    const byte = value % 128;
    value = Math.floor(value / 128);
    result.push(byte + (value ? 128 : 0));
  } while (value);
  return result;
}
function message(field, bytes) {
  return [...varint(field * 8 + 2), ...varint(bytes.length), ...bytes];
}
function scalar(field, value) {
  return [...varint(field * 8), ...varint(value)];
}
function fields(bytes) {
  let position = 0;
  const result = new Map();
  function takeVarint() {
    let value = 0, factor = 1, byte;
    do {
      assert.ok(position < bytes.length, "protobuf fixture truncated");
      byte = bytes[position++];
      value += (byte & 127) * factor;
      factor *= 128;
    } while (byte & 128);
    return value;
  }
  while (position < bytes.length) {
    const tag = takeVarint(), field = Math.floor(tag / 8), wire = tag % 8;
    let value;
    if (wire === 0) value = takeVarint();
    else if (wire === 2) {
      const length = takeVarint();
      assert.ok(position + length <= bytes.length, "protobuf fixture length invalid");
      value = bytes.slice(position, position + length);
      position += length;
    } else assert.fail(`unexpected fixture wire type ${wire}`);
    if (!result.has(field)) result.set(field, []);
    result.get(field).push(value);
  }
  return result;
}
function child(parent, field) {
  assert.equal(parent.get(field)?.length, 1, `expected one child for field ${field}`);
  return fields(parent.get(field)[0]);
}
function run(path, bytes) {
  let output, doneCount = 0, networkCalls = 0;
  const logs = [];
  const values = new Map();
  const context = vm.createContext({
    console: { log: (...args) => logs.push(args.join(" ")) },
    TextDecoder, TextEncoder,
    $task: { fetch: () => { networkCalls++; throw new Error("network forbidden"); } },
    $prefs: {
      valueForKey: key => values.get(key) ?? null,
      setValueForKey: (value, key) => { values.set(key, value); return true; },
    },
    $notify: () => { throw new Error("unexpected notification"); },
    $done: value => { output = value; doneCount++; },
    __fixtureBytes: bytes,
  });
  // ArrayBuffer and Uint8Array must originate in the VM realm, as on QuanX.
  vm.runInContext(`
    globalThis.$request = {
      url: "https://youtubei.googleapis.com/youtubei/v1/${path}?prettyPrint=false",
      method: "POST", headers: {"user-agent": "com.google.ios.youtube/20.01"}
    };
    globalThis.$response = {
      statusCode: 200, headers: {"content-type": "application/x-protobuf"},
      bodyBytes: new Uint8Array(__fixtureBytes).buffer
    };
  `, context);
  vm.runInContext(source, context, { timeout: 2000, filename: "youtube-background.js" });
  assert.equal(doneCount, 1, "QuanX callback must be called once");
  assert.equal(networkCalls, 0, "response-only hook must not make remote requests");
  return { output, logs };
}
function assertPlayer(bytes) {
  const player = fields(bytes);
  assert.ok(!player.has(7), "player adPlacements must be removed");
  assert.ok(!player.has(68), "player adSlots must be removed");
  assert.equal(player.get(99)?.[0], 7, "unrecognized player fields must be preserved");
  const status = child(player, 2);
  const background = child(child(status, 11), 64657230);
  assert.equal(background.get(1)?.[0], 1, "background playback must be enabled");
  const pip = child(child(status, 21), 151635310);
  assert.equal(pip.get(1)?.[0], 1, "picture-in-picture must be enabled");
  assert.equal(pip.get(8)?.[0], 1, "author PiP mode must be retained");
}
function outputBytes(result) {
  assert.equal(Object.prototype.toString.call(result.output.bodyBytes), "[object ArrayBuffer]",
    "QuanX must receive a binary ArrayBuffer, not an object/string/Uint8Array");
  assert.ok(!Object.hasOwn(result.output, "body"), "binary output must not become text");
  assert.deepEqual(result.logs, [], "valid protobuf must not take the error exit");
  return Array.from(new Uint8Array(result.output.bodyBytes));
}

// Root Player: playabilityStatus plus one ad placement, one ad slot, unknown data.
const playerInput = [...message(2, []), ...message(7, []), ...message(68, []), ...scalar(99, 7)];
assertPlayer(outputBytes(run("player", playerInput)));

// get_watch transports player responses under Watch.contents[].player.
const watchInput = message(1, message(2, playerInput));
const watch = fields(outputBytes(run("get_watch", watchInput)));
const nestedPlayer = child(watch, 1).get(2)[0];
assertPlayer(nestedPlayer);

// Settings response installs a background-playback renderer for the client UI.
const settings = fields(outputBytes(run("account/get_setting", [])));
const renderer = child(child(settings, 6), 88478200);
assert.ok(renderer.size > 0, "background settings renderer must be written");

// Invalid protobuf and missing required status fail open through an empty $done.
for (const invalid of [[255], []]) {
  const result = run("player", invalid);
  assert.deepEqual(Object.keys(result.output), []);
  assert.ok(result.logs.length > 0, "invalid player must use the author's caught-error exit");
}
console.log(JSON.stringify({
  passed: ["player ads/background/PiP", "nested get_watch player", "background settings",
    "QuanX ArrayBuffer callback", "unknown field preservation", "no network", "malformed fail-open"],
}));
