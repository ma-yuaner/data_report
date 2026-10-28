<template>
  <section class="product-guide">
    <template v-if="mode === 'fields'"
      ><h2>字段含义、来源与可编辑范围</h2>
      <p class="muted">对应当前页面或办理步骤。条件必填随处理方式显示，已审核内容锁定。</p>
      <article v-for="field in fieldsFor(node)" :key="field.name" class="field-contract">
        <h3>{{ field.name }}</h3>
        <p>{{ field.meaning }}</p>
        <dl>
          <dt>来源 / 默认</dt>
          <dd>{{ field.source }}</dd>
          <dt>能否修改</dt>
          <dd>{{ field.edit }}</dd>
          <dt>填写与影响</dt>
          <dd>{{ field.rule }}</dd>
        </dl>
      </article>
      <p v-if="!fieldsFor(node).length">
        本页为说明或历史记录，无独立录入字段；单据字段可在“功能模块”选择对应办理页面查看。
      </p>
    </template>
    <template v-else
      ><h2>按钮条件与操作后去向</h2>
      <article v-for="flow in actionsFor(node)" :key="flow.name" class="field-contract">
        <h3>{{ flow.name }}</h3>
        <p><strong>何时可用：</strong>{{ flow.when }}</p>
        <p><strong>点击后：</strong>{{ flow.result }}</p>
      </article>
      <p class="muted">
        “切换下一处理人”只切换模拟角色并打开同单待办；不会自动批准或完成业务。导航切页不改变处理状态，保存或提交成功后才更新。
      </p></template
    >
  </section>
</template>
<script setup lang="ts">
import { fieldsFor, actionsFor } from './product-spec'
defineProps<{ node: string; mode: 'fields' | 'flows' }>()
</script>
