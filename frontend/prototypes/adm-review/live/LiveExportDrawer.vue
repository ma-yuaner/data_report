<template>
  <a-drawer v-model:open="exportStore.drawerOpen" title="导出任务（本机模拟）" :get-container="false" :width="560" :root-style="{position:'absolute'}">
    <p>文件由当前演示条件生成，不连接后台任务队列。</p>
    <article v-for="item in exportStore.items" :key="item.id"><h3>{{item.name}}</h3><p>{{item.status}}</p><a-button @click="download(item.name,item.content)">下载本机文件</a-button></article>
    <a-empty v-if="!exportStore.items.length" description="暂无任务，请在业务页面点击导出" />
  </a-drawer>
</template>
<script setup lang="ts">
import { exportStore } from './exports'
function download(name:string,content:string){const url=URL.createObjectURL(new Blob(['\uFEFF',content],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
</script>
