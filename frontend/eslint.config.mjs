import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import ts from 'typescript-eslint'

export default ts.config(
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['**/*.{ts,vue,mjs}'],
    extends: [js.configs.recommended, ...ts.configs.recommended, ...vue.configs['flat/essential']],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { parser: ts.parser },
    },
    rules: {
      // 历史代码的类型收紧和未使用符号单独迁移，不混入本轮结构调整。
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'vue/multi-word-component-names': 'off',
    },
  },
)
