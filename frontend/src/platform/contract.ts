// Copied verbatim from ediarum-platform src/contract.ts at commit ef2957c — do not edit;
// update by copying the platform's file again.

/**
 * ediarum.platform mount contract.
 *
 * This file is the reference that every app frontend (ediarum.webdav, ediarum.zotero,
 * ediarum.index, …) implements to be hosted inside the platform. It is intentionally
 * self-contained (no imports), so app repositories can copy it verbatim into their
 * source tree as `src/platform/contract.ts`. Auth is covered by a separate contract,
 * `docs/auth-contract.md`.
 *
 * How the platform uses it:
 *
 * 1. The platform reads `/config/apps.json` and, for each app, registers the
 *    route `/<id>/…`.
 * 2. When the user opens such a route, the platform loads the app's `entry` URL
 *    (e.g. `/apps/zotero/embed.js`) with a native dynamic `import()`.
 * 3. It checks that the module exports `contractVersion === CONTRACT_VERSION` and a
 *    `mount` function (see {@link AppModule}). Otherwise it shows an error.
 * 4. It calls `mount(el, ctx)` with an empty element that fills the content area,
 *    and keeps the returned unmount function. If the app's header contains the platform
 *    controls (`<ediarum-home>`, `<ediarum-user-menu>`), the platform hides its own top bar;
 *    see `docs/integrating-an-app.md`, 3.10.
 * 5. When the user switches to another app, logs out, or leaves the app's routes,
 *    the platform calls the unmount function and then removes `el`.
 *
 * Navigation within the app (`/zotero/a` → `/zotero/b`) does NOT
 * remount the app: the app's own router (created with `createWebHistory(ctx.routerBase)`)
 * handles it. The platform router and the app router share `window.history`.
 *
 * See `docs/integrating-an-app.md` for a step-by-step guide.
 */

/**
 * Version of this contract. The platform refuses to mount a module whose
 * `contractVersion` differs. Bumped only for breaking changes.
 */
export const CONTRACT_VERSION = 1

/** The logged-in user, as reported by the auth backend. */
export interface PlatformUser {
  /** Display name. */
  name: string
  /** Role names, e.g. `['admin']`. Empty for regular users. */
  roles: string[]
  /**
   * Slugs of the projects the user is a member of, e.g. `['schleiermacher']`. Users with the
   * role `admin` may access every project, member or not. Names: `GET /api/auth/projects`.
   * See docs/auth-contract.md, "Projects".
   */
  projects: string[]
}

/** Everything the platform passes to an app when mounting it. */
export interface MountContext {
  /**
   * Router base for the app, always with leading and trailing slash,
   * e.g. `'/zotero/'`. Use it with `createWebHistory(ctx.routerBase)`.
   */
  routerBase: string
  /**
   * Base URL for the app's backend, without trailing slash, e.g. `'/api/zotero'`.
   * Prefix every API request with it. Requests are same-origin and authenticated by the
   * session cookie, so use `credentials: 'same-origin'` (the fetch default) or, with axios,
   * `withCredentials` is not needed.
   */
  apiBase: string
  /** The logged-in user at mount time. The app is remounted if the user changes. */
  user: PlatformUser
  /**
   * Call on any 401 response from the app's backend. The platform clears its session state,
   * unmounts the app and sends the user to the login page; after logging in, the user is
   * returned to the current URL. Do not show your own login UI.
   */
  onUnauthorized: () => void
}

/**
 * Mounts the app into `el` and returns a function that fully unmounts it.
 *
 * `mount` must be synchronous. The unmount function must undo everything `mount` did:
 * `app.unmount()`, remove global event listeners, stop timers, close sockets, and remove
 * any DOM the app added outside `el` (e.g. teleported dialogs or injected `<style>` tags
 * that are not shared). After it returns, the app must not touch `window.history`.
 */
export type Mount = (el: HTMLElement, ctx: MountContext) => () => void

/** Shape of the ES module found at an app's `entry` URL. */
export interface AppModule {
  mount: Mount
  contractVersion: number
}
