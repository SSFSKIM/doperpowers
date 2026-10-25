// Route a response by content type (the header, else a sniff of its first
// bytes) to its kind and main file, and decode text in its declared charset.

export type Kind = 'html' | 'markdown' | 'text' | 'json' | 'pdf' | 'image' | 'binary'

export type Route = { kind: Kind; mediaType: string; file: string }

const IMAGE_EXT: Record<string, string> = {
  'image/png': 'png', 'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/pjpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp',
  'image/svg+xml': 'svg', 'image/avif': 'avif', 'image/bmp': 'bmp', 'image/x-icon': 'ico', 'image/vnd.microsoft.icon': 'ico',
  'image/tiff': 'tiff', 'image/heic': 'heic',
}

const FILE_EXT: Record<string, string> = {
  'application/zip': 'zip', 'application/gzip': 'gz', 'application/x-gzip': 'gz', 'application/x-tar': 'tar',
  'application/octet-stream': 'bin', 'application/wasm': 'wasm', 'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'audio/mpeg': 'mp3', 'video/mp4': 'mp4', 'font/woff2': 'woff2',
}

/** The media type of a Content-Type header, lowercased, without parameters. */
export function mediaTypeOf(contentType: string | undefined): string {
  return (contentType ?? '').split(';')[0].trim().toLowerCase()
}

/** The extension an image of this media type is saved with, or null when it is not an image. */
export function imageExtension(mediaType: string): string | null {
  if (IMAGE_EXT[mediaType]) return IMAGE_EXT[mediaType]
  if (!mediaType.startsWith('image/')) return null
  return mediaType.slice(6).replace(/^x-/, '').replace(/\+.*$/, '').replace(/[^a-z0-9]/g, '') || 'img'
}

/** A media type from the first bytes, for a response without a useful header. */
export function sniff(body: Buffer): string {
  const head = body.subarray(0, 1024)
  const ascii = head.toString('latin1')
  if (ascii.startsWith('%PDF-')) return 'application/pdf'
  if (head[0] === 0x89 && ascii.slice(1, 4) === 'PNG') return 'image/png'
  if (head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) return 'image/jpeg'
  if (ascii.startsWith('GIF87a') || ascii.startsWith('GIF89a')) return 'image/gif'
  if (ascii.startsWith('RIFF') && ascii.slice(8, 12) === 'WEBP') return 'image/webp'
  if (ascii.slice(4, 12) === 'ftypavif') return 'image/avif'
  if (head.includes(0)) return 'application/octet-stream'
  const text = ascii.replace(/^﻿|^\xEF\xBB\xBF/, '').trimStart().toLowerCase()
  if (text.startsWith('<!doctype html') || text.startsWith('<html') || /^<(head|body|meta|title)\b/.test(text)) return 'text/html'
  if (text.startsWith('<svg')) return 'image/svg+xml'
  if (text.startsWith('<?xml') || text.startsWith('<rss') || text.startsWith('<feed')) return 'application/xml'
  if (text.startsWith('{') || text.startsWith('[')) {
    try { JSON.parse(body.toString('utf8')); return 'application/json' } catch {}
  }
  return 'text/plain'
}

export function route(contentType: string | undefined, body: Buffer): Route {
  let mediaType = mediaTypeOf(contentType)
  if (!mediaType || mediaType === 'application/octet-stream' || mediaType === 'binary/octet-stream') mediaType = sniff(body)
  const r = (kind: Kind, file: string): Route => ({ kind, mediaType, file })
  if (mediaType === 'text/html' || mediaType === 'application/xhtml+xml') return r('html', 'page.md')
  if (mediaType === 'text/markdown' || mediaType === 'text/x-markdown') return r('markdown', 'page.md')
  if (mediaType === 'application/json' || mediaType.endsWith('+json')) return r('json', 'page.json')
  if (mediaType === 'application/pdf') return r('pdf', 'page.pdf')
  const imageExt = imageExtension(mediaType)
  if (imageExt) return r('image', `image.${imageExt}`)
  if (mediaType.startsWith('text/') || mediaType.endsWith('/xml') || mediaType.endsWith('+xml') || mediaType === 'application/javascript')
    return r('text', 'page.txt')
  const ext = FILE_EXT[mediaType] ?? (mediaType.split('/')[1] ?? 'bin').replace(/^x-/, '').replace(/[^a-z0-9]/g, '').slice(0, 10)
  return r('binary', `file.${ext || 'bin'}`)
}

/** Decodes text by its charset: the header's, else (for HTML) a meta tag's, else a BOM, else UTF-8. */
export function decodeText(body: Buffer, contentType: string | undefined, html: boolean): string {
  let label = /charset\s*=\s*"?([\w.:-]+)/i.exec(contentType ?? '')?.[1]
  if (!label && html) {
    const head = body.subarray(0, 2048).toString('latin1')
    label = /<meta[^>]+charset\s*=\s*["']?([\w.:-]+)/i.exec(head)?.[1]
  }
  if (!label && body[0] === 0xff && body[1] === 0xfe) label = 'utf-16le'
  if (!label && body[0] === 0xfe && body[1] === 0xff) label = 'utf-16be'
  let decoder: TextDecoder
  try { decoder = new TextDecoder(label ?? 'utf-8') } catch { decoder = new TextDecoder('utf-8') }
  return decoder.decode(body)
}
