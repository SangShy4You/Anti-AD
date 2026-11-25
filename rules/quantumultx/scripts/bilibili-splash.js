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

  let removed = 0;
  for (const key of ["list", "show"]) {
    const entries = result.data[key];
    if (!Array.isArray(entries)) continue;

    const remaining = entries.filter(entry => !entry || !(
      entry.is_ad === true || entry.is_ad === 1 ||
      (typeof entry.ad_cb === "string" && entry.ad_cb.trim() !== "")
    ));
    removed += entries.length - remaining.length;
    result.data[key] = remaining;
  }

  $done(removed ? { body: JSON.stringify(result) } : {});
})();
