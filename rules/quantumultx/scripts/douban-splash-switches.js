// QX response handler for the splash-specific settings in Douban's feature flags.
(function () {
  if ($request.method !== "GET" || typeof $response.body !== "string") {
    $done({});
    return;
  }

  let flags;
  try {
    flags = JSON.parse($response.body);
  } catch {
    $done({});
    return;
  }
  if (!flags || typeof flags !== "object") {
    $done({});
    return;
  }

  let changed = false;
  for (const key of ["enable_splash_client_bid", "splash_client_bid_use_preload"]) {
    if (flags[key] === true) {
      flags[key] = false;
      changed = true;
    }
  }
  if (Array.isArray(flags.splash_sdk_info) && flags.splash_sdk_info.length > 0) {
    flags.splash_sdk_info = [];
    changed = true;
  }

  $done(changed ? { body: JSON.stringify(flags) } : {});
})();
