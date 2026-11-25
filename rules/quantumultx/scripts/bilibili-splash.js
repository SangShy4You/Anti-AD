// QX script-response-body for the Bilibili iOS splash list and display APIs.
(function () {
  if ($request.method !== "GET" || typeof $response.body !== "string") {
    $done({});
    return;
  }

  let result;
  try {
    result = JSON.parse($response.body);
  } catch {
    $done({});
    return;
  }
  if (!result || result.code !== 0 || !result.data) {
    $done({});
    return;
  }

  let changed = false;
  for (const key of ["list", "show"]) {
    const entries = result.data[key];
    if (!Array.isArray(entries)) continue;

    const remaining = entries.filter(entry => !entry || !(
      entry.is_ad === true || entry.is_ad === 1 ||
      (typeof entry.ad_cb === "string" && entry.ad_cb.trim() !== "")
    ));
    if (remaining.length !== entries.length) {
      result.data[key] = remaining;
      changed = true;
    }
  }

  const { list, show, keep_ids } = result.data;
  if (Array.isArray(list) && list.length === 0 &&
      Array.isArray(show) && show.length === 0 &&
      Array.isArray(keep_ids) && keep_ids.length > 0) {
    result.data.keep_ids = [];
    changed = true;
  }

  $done(changed ? { body: JSON.stringify(result) } : {});
})();
