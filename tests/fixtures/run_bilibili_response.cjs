/* Run only the previously reviewed release, using synthetic QX inputs. */
"use strict";
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");

const bytes = fs.readFileSync(process.argv[2]);
assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"),
  "e8768eb5c75bbfaea78f5798ac7827c431f81a61416a7877753f36dd36b9cb60",
  "Review the new release before running its script");
const bundle = new vm.Script(bytes.toString("utf8"), { filename: "biliverse-response.js" });

async function run(url, data, isGrpc = false) {
  let output;
  const prefs = new Map();
  const logs = [];
  const context = vm.createContext({
    console: { log: (...args) => logs.push(args.join(" ")) },
    URL, TextEncoder, TextDecoder,
    $task: { fetch: () => { assert.fail("Unexpected network call for this fixture"); } },
    $prefs: {
      valueForKey: key => prefs.get(key) ?? null,
      setValueForKey: (value, key) => { prefs.set(key, value); return true; },
    },
    $done: value => { assert.equal(output, undefined); output = value; },
    $request: { url, method: isGrpc ? "POST" : "GET", headers: {} },
    data, isGrpc,
  }, { codeGeneration: { strings: false, wasm: false } });
  vm.runInContext(`
    globalThis.$response = {
      headers: {"content-type": isGrpc ? "application/grpc" : "application/json"},
      ...(isGrpc ? {bodyBytes: Uint8Array.from(data).buffer} : {body: JSON.stringify(data)})
    };
  `, context);
  bundle.runInContext(context, { timeout: 2000 });
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(output, "No QX response callback: " + logs.join("\n"));
  return isGrpc ? Array.from(new Uint8Array(output.bodyBytes)) : JSON.parse(output.body);
}

async function main() {
  const video = { id: 11, card_type: "small_cover_v9", card_goto: "av" };
  const ad = { id: 12, card_type: "cm_double_v9", card_goto: "ad_inline_av" };
  const feed = await run("https://app.bilibili.com/x/v2/feed/index?device=phone",
    { code: 0, data: { items: [ad, video] } });
  assert.deepEqual(feed.data.items, [video], "home feed should preserve the ordinary video");

  const live = { roomid: 11, is_ad: 0 };
  const promotedRoom = { roomid: 12, show_ad_icon: 1 };
  const liveApi = "https://api.live.bilibili.com/xlive/";
  const card = small_card_v1 => ({ card_data: { small_card_v1 } });
  const liveFeed = await run(liveApi + "app-interface/v2/index/feed",
    { data: { card_list: [card(promotedRoom), card(live)] } });
  assert.deepEqual(liveFeed.data.card_list, [card(live)]);
  const roomRecs = await run(liveApi + "app-interface/v2/room/recList",
    { data: { list: [live, promotedRoom] } });
  assert.deepEqual(roomRecs.data.list, [live]);
  const room = await run(liveApi + "app-room/v1/index/getInfoByRoom", {
    data: { roomid: 11, activity_banner_info: {}, shopping_info: { is_show: 1 },
      new_tab_info: { outer_list: [{ biz_id: 33 }, { biz_id: 1 }] } },
  });
  assert.deepEqual(room.data, { roomid: 11, shopping_info: { is_show: 0 },
    new_tab_info: { outer_list: [{ biz_id: 1 }] } });

  // All fixture fields and lengths fit in one byte. DynamicList.list contains
  // a regular (type 1) and a sponsored (type 15) card. Field 2 is the UP list.
  const message = (field, body) => [(field << 3) | 2, body.length, ...body];
  const cardOfType = type => message(1, [8, type]);
  const frame = body => [0, 0, 0, 0, body.length, ...body];
  const upList = message(2, []);
  const topicList = message(3, []);
  for (const method of ["DynAll", "DynVideo"]) {
    const dynamicUrl = "https://grpc.biliapi.net/bilibili.app.dynamic.v2.Dynamic/" + method;
    const body = [...message(1, [...cardOfType(15), ...cardOfType(1)]), ...upList];
    if (method === "DynAll") body.push(...topicList);
    const result = await run(dynamicUrl, frame(body), true);
    const expected = [...message(1, cardOfType(1)), ...upList];
    assert.deepEqual(result, frame(expected), method + " should preserve the regular card and UP list");
  }
  console.log("PASS: home feed, both dynamic feeds and three live endpoints");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
