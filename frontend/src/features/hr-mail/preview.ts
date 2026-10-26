/** This derivative is only for display. The server's frozen email is never edited. */
export function sandboxDocument(html: string): string {
  const document = new DOMParser().parseFromString(html, 'text/html')
  document.querySelectorAll('script,meta,base,link,iframe,frame,object,embed,form').forEach((node) => node.remove())
  document.querySelectorAll('*').forEach((element) => {
    for (const attribute of [...element.attributes]) {
      if (
        /^on/i.test(attribute.name) ||
        ['href', 'srcset', 'action', 'formaction', 'srcdoc', 'ping', 'background'].includes(
          attribute.name.toLowerCase(),
        )
      ) {
        element.removeAttribute(attribute.name)
      }
    }
  })
  const policy = document.createElement('meta')
  policy.httpEquiv = 'Content-Security-Policy'
  policy.content =
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; media-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'"
  document.head.prepend(policy)
  return `<!doctype html>${document.documentElement.outerHTML}`
}
