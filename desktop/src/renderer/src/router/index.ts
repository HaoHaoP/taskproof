/**
 * Hash history, because the production renderer is loaded over `file://`.
 *
 * Two rules learned the hard way:
 *  - a redirect record must NOT carry a `name` (a duplicate name makes
 *    vue-router drop a route silently and `route.name` ends up undefined),
 *  - keep a catch-all so an unknown hash still lands on a real view.
 */
import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: () => '/matrix' },
    { path: '/matrix/:taskId?', name: 'matrix', component: () => import('../views/MatrixView.vue') },
    {
      path: '/projects/:taskId?',
      name: 'projects',
      component: () => import('../views/ProjectsView.vue')
    },
    { path: '/tasks/:taskId?', name: 'tasks', component: () => import('../views/TasksView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: () => '/matrix' }
  ]
})
