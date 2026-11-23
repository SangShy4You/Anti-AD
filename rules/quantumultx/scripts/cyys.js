// Personal integration: Replace the unavailable upstream replacement picture with a maintained transparent PNG; keep the miniapp's original ad-response cleanup and GPL attribution.
// Upstream: https://raw.githubusercontent.com/fmz200/wool_scripts/58f6cce6dbd5c5fe50c2998938f9c2ba631a7c18/Scripts/cyys.js
let obj=JSON.parse($response.body);
delete obj.data.INDEX_SLOT_01;
delete obj.data.INDEX_SLOT_02;
obj.data?.INDEX_TOP_BANNER?.contents?.forEach(item => {
  delete item.bubble; 
  delete item.figure; 
  item.value = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/assets/transparent.png";
});
$done({body: JSON.stringify(obj)});
