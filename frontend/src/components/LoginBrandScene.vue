<template>
  <svg class="login-scene" viewBox="0 0 560 320" aria-hidden="true" focusable="false">
    <defs><pattern id="login-scene-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".8" fill="#cee0e4" /></pattern></defs>
    <rect width="560" height="320" fill="url(#login-scene-grid)" />
    <g fill="none" stroke="#b8d6d9" stroke-width="1">
      <ellipse cx="280" cy="165" rx="210" ry="98" transform="rotate(-18 280 165)" />
      <ellipse cx="280" cy="165" rx="143" ry="119" transform="rotate(24 280 165)" />
      <path d="M95 90L280 165 455 75M100 245L280 165 470 230" />
    </g>
    <g fill="white" stroke="#cbdfe2"><rect x="30" y="64" width="122" height="48" rx="8" /><rect x="401" y="51" width="125" height="48" rx="8" /><rect x="27" y="218" width="132" height="48" rx="8" /><rect x="407" y="207" width="126" height="48" rx="8" /></g>
    <g fill="#506e77" font-size="13" text-anchor="middle"><text x="91" y="94">业务数据</text><text x="464" y="81">统一指标</text><text x="93" y="248">数据资产</text><text x="470" y="237">经营洞察</text></g>
    <circle cx="280" cy="165" r="67" fill="#e4f3f3" /><circle cx="280" cy="165" r="51" fill="white" stroke="#b7dadd" />
    <image :href="symbol" x="247" y="139" width="66" height="43" />
    <g fill="#40b3b6"><circle cx="185" cy="77" r="5" /><circle cx="351" cy="260" r="5" /><circle cx="485" cy="143" r="4" /></g>
  </svg>
</template>
<script setup lang="ts">
import symbol from '@/assets/brand/company-symbol.png'
</script>
<style scoped>
.login-scene { display: block; width: 100%; max-width: 540px; margin: 32px 0 10px; }
</style>
