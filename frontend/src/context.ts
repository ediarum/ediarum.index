import type { Http } from '@/api/client'
import type { MountContext } from '@/platform/contract'
import { inject, type InjectionKey, ref, type Ref } from 'vue'
import { createHttp } from '@/api/client'

export interface SearchFieldOption {
  title: string
  value: string
}

/** Everything one mount of the app shares — created per mount (never at module
 *  level, so nothing survives into the next user's mount), provided to the
 *  component tree by `embed.ts`. */
export interface AppContext {
  http: Http
  platform: MountContext
  /** platform role `admin`: every project, `/keys`, `/ingest-runs` */
  isAdmin: boolean
  /** the entries search: the toolbar input writes it, the entries list reads it */
  search: { term: Ref<string>; field: Ref<string>; fields: Ref<SearchFieldOption[]> }
  dispose: () => void
}

export const APP_CONTEXT: InjectionKey<AppContext> = Symbol('ediarum-index')

export function createAppContext(platform: MountContext): AppContext {
  const http = createHttp(platform)
  return {
    http,
    platform,
    isAdmin: platform.user.roles.includes('admin'),
    search: {
      term: ref(''),
      field: ref('label'),
      fields: ref<SearchFieldOption[]>([{ title: 'Label', value: 'label' }]),
    },
    dispose: () => http.dispose(),
  }
}

export function useAppContext(): AppContext {
  const context = inject(APP_CONTEXT)
  if (!context) throw new Error('ediarum.index: no app context — mounted outside embed.ts?')
  return context
}

/** The mount's backend client. */
export function useHttp(): Http {
  return useAppContext().http
}
