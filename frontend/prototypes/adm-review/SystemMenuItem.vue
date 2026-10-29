<template>
  <details v-if="node.children.length" class="system-menu-group" :open="node.id==='adm' || containsActive(node)">
    <summary :class="{'system-active':containsActive(node)}">{{ node.title }}</summary>
    <div class="system-menu-children"><SystemMenuItem v-for="child in node.children" :key="child.id" :node="child" :active="active" @select="emit('select',$event)" /><slot v-if="node.id==='adm'" /></div>
  </details>
  <button v-else :class="{'active':node.id===active}" :aria-current="node.id===active?'page':undefined" :disabled="node.disabled" :title="node.disabled?'正式系统原有预留入口':node.route" @click="emit('select',node)">{{ node.title }}<small v-if="node.disabled">原系统预留</small></button>
</template>
<script setup lang="ts">
import type { SystemMenuNode } from './system-navigation'
const props=defineProps<{node:SystemMenuNode;active:string}>()
const emit=defineEmits<{select:[node:SystemMenuNode]}>()
function containsActive(node:SystemMenuNode):boolean {return node.id===props.active || (node.id==='adm' && props.active==='adm') || node.children.some(containsActive)}
</script>
