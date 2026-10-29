import { reactive } from 'vue'
export const demoPeople = [
  { id:'coordinator', name:'林协调', role:'协调人', isAdmin:true },
  { id:'handlerA', name:'陈承办', role:'承办人', isAdmin:false },
  { id:'handlerB', name:'周承办', role:'承办人', isAdmin:false },
  { id:'reviewer', name:'许审核', role:'审核人', isAdmin:false },
  { id:'finance', name:'何财务', role:'财务', isAdmin:false },
]
const permissions=['view','handle','create','edit','assign','import','export','scope.team','scope.all','review','finance','close','coordinate'].map(name=>`adm.${name}`)
const auth=reactive({async logout(){setDemoPerson('coordinator')},user:{id:'coordinator',username:'coordinator',displayName:'林协调',isAdmin:true,permissions}})
export function useAuthStore(){return auth}
export function setDemoPerson(id:string){const person=demoPeople.find(item=>item.id===id);if(person){const names=person.isAdmin?permissions:['view','export',...(person.role==='承办人'?['handle','edit']:person.role==='审核人'?['review']:['finance'])].map(name=>`adm.${name}`);Object.assign(auth.user,{id:person.id,username:person.id,displayName:person.name,isAdmin:person.isAdmin,permissions:names})}}
