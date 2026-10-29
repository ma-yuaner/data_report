<template><div class="page-wrap"><h1>{{selected?.title || '原系统入口'}}</h1><a-alert type="info" message="保留原系统菜单位置；本轮制作ADM与资源治理原页面原型，其他模块尚未接入演示。" show-icon /><p>{{route.path}}</p><p>本页不加载正式账号、数据或接口。账号/权限复用系统管理，通知优先适配监控中心，导出复用页头任务入口。</p><router-link to="/adm/workbench">返回ADM我的工作台</router-link></div></template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { systemMenus,type SystemMenuNode } from '../system-navigation'
const route=useRoute()
const flatten=(nodes:SystemMenuNode[]):SystemMenuNode[]=>nodes.flatMap(node=>[node,...flatten(node.children)])
const selected=computed(()=>flatten(systemMenus).find(node=>node.route===route.path))
</script>
