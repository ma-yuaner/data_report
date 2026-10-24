<template><div class="shared-form-grid"><slot /></div></template>
<style scoped>
.shared-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.shared-form-grid :deep(> label) { display: flex; flex-direction: column; align-items: stretch; gap: 6px; min-width: 0; color: #334155; font-size: 14px; }
.shared-form-grid :deep(.adm-span), .shared-form-grid :deep(.form-span) { grid-column: 1 / -1; }
.shared-form-grid :deep(.ant-select), .shared-form-grid :deep(.ant-picker) { width: 100%; }
.shared-form-grid :deep(.ant-switch) { align-self: flex-start; }
.shared-form-grid :deep(.required) { color: #b91c1c; }
@media (max-width: 640px) { .shared-form-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
