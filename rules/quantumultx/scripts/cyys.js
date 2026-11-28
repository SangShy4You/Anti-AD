// Personal integration: Replace the unavailable upstream replacement picture with a maintained transparent PNG; keep the miniapp's original ad-response cleanup and GPL attribution.
// Upstream: https://raw.githubusercontent.com/fmz200/wool_scripts/d875bc946ed8a6a9606ef40d29bf55a7c8435e08/Scripts/cyys.js
let obj=JSON.parse($response.body);
delete obj.data.INDEX_SLOT_01;
delete obj.data.INDEX_SLOT_02;
obj.data?.INDEX_TOP_BANNER?.contents?.forEach(item => {
  delete item.bubble; 
  delete item.figure; 
  item.value = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/assets/transparent.png";
});
$done({body: JSON.stringify(obj)});
