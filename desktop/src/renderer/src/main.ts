import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'

import '@unocss/reset/tailwind.css'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'uno.css'
import './assets/tokens.css'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'

createApp(App).use(createPinia()).use(router).use(i18n).use(ElementPlus).mount('#app')
