import type { RouteRecordRaw } from 'vue-router'
import { inject } from 'vue'
import { APP_CONTEXT } from '@/context'

/** Platform admins only — the backend answers 403 anyway; this keeps a
 *  non-admin from landing on an empty page. (Only ever reached by navigating
 *  inside the app, so the redirect can't rewrite a platform URL.) */
function adminOnly() {
  return inject(APP_CONTEXT)?.isAdmin ? true : { name: 'projects' }
}

/** The app's routes, relative to the platform's `/index/` (`ctx.routerBase`). */
export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'projects', component: () => import('@/views/ProjectsList.vue') },
  {
    path: '/ingest-runs',
    name: 'ingest-runs',
    component: () => import('@/views/IngestRunsList.vue'),
    beforeEnter: adminOnly,
  },
  {
    path: '/keys',
    name: 'keys',
    component: () => import('@/views/KeysList.vue'),
    beforeEnter: adminOnly,
  },
  {
    path: '/:project([a-z0-9-]+)',
    name: 'entries',
    component: () => import('@/views/EntriesList.vue'),
    props: true,
  },
  // a page, never a redirect: see NotFound.vue
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFound.vue') },
]
