<template>
 <a-modal :open="open" title="原因与跟进信息" :confirm-loading="saving" :ok-button-props="{disabled:loading || !!error}" @ok="save" @cancel="$emit('close')">
  <a-alert v-if="error" type="error" :message="error" />
  <a-spin :spinning="loading"><a-form layout="vertical">
   <a-form-item label="根本原因分类"><a-select v-model:value="form.causeCategory" :options="causeOptions" /></a-form-item>
   <a-form-item label="原因说明"><a-textarea v-model:value="form.causeDetail" :maxlength="2000" /></a-form-item>
   <a-form-item label="涉及环节"><a-input v-model:value="form.responsibleLink" :maxlength="2000" placeholder="例如订位、出票、退款" /></a-form-item>
   <a-form-item label="证据说明"><a-textarea v-model:value="form.evidenceNote" :maxlength="2000" placeholder="可引用已有附件名称" /></a-form-item>
   <a-form-item label="当前阻塞原因"><a-textarea v-model:value="form.blockingReason" :maxlength="2000" /></a-form-item>
  </a-form></a-spin>
 </a-modal>
</template>
<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { operationsApi, causeOptions } from './operationsApi'
import { errorText, type Fields } from './api'
const props = defineProps<{open:boolean;caseId:number;lineId:number}>()
const emit = defineEmits(['close','saved'])
const form=reactive<Fields>({}),loading=ref(false),saving=ref(false),error=ref('')
let request=0
watch(() => [props.open,props.caseId,props.lineId], async () => {
 const seq=++request
 if(!props.open || !props.lineId) return
 loading.value=true;error.value=''
 try { const data=await operationsApi.context(props.caseId,props.lineId);if(seq!==request)return
 Object.assign(form,{causeCategory:data.causeCategory||'UNKNOWN',causeDetail:data.causeDetail||'',evidenceNote:data.evidenceNote||'',blockingReason:data.blockingReason||'',responsibleLink:data.responsibleLink||''})
 }catch(e){if(seq===request)error.value=errorText(e)}finally{if(seq===request)loading.value=false}
})
async function save(){if(saving.value)return;saving.value=true;try{await operationsApi.saveContext(props.caseId,props.lineId,form);void message.success('原因与跟进信息已保存');emit('saved');emit('close')}catch(e){void message.error(errorText(e))}finally{saving.value=false}}
</script>
