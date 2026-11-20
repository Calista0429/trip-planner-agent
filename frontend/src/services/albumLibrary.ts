import { ALBUM_STYLES, type Album, type AlbumFailure, type AlbumPicture } from '@/types'

/**
 * Albums generated in this browser. The comic service has no list endpoint, so
 * "my albums" is whatever this browser saved: text and image URLs only, never
 * the images themselves.
 */
export const ALBUM_LIBRARY_KEY = 'tripPlanner.albums.v1'
export const MAX_SAVED_ALBUMS = 30

type Unknown = Record<string, unknown>

const isObject = (v: unknown): v is Unknown => !!v && typeof v === 'object' && !Array.isArray(v)
const isString = (v: unknown): v is string => typeof v === 'string'
const isWebUrl = (v: unknown): v is string => isString(v) && /^https?:\/\//i.test(v)

function parsePicture(raw: unknown): AlbumPicture | null {
  if (!isObject(raw) || !isWebUrl(raw.imageUrl)) return null
  const { description, location, pointsOfInterest } = raw
  if (!isString(description) || !isString(location) || !isString(pointsOfInterest)) return null
  return { imageUrl: raw.imageUrl, description, location, pointsOfInterest }
}

function parseFailure(raw: unknown): AlbumFailure | null {
  return isObject(raw) && isString(raw.file) && isString(raw.reason) ? { file: raw.file, reason: raw.reason } : null
}

/** Rebuild an album from untrusted JSON, field by field; anything off returns null. */
function parseAlbum(raw: unknown): Album | null {
  if (!isObject(raw)) return null
  const { tripId, title, style, createdAt, pictures, failed } = raw
  if (!isString(tripId) || !tripId || !isString(title)) return null
  if (!ALBUM_STYLES.includes(style as Album['style'])) return null
  if (!isString(createdAt) || Number.isNaN(Date.parse(createdAt))) return null
  if (!Array.isArray(pictures) || !Array.isArray(failed)) return null
  const parsedPictures = pictures.map(parsePicture)
  const parsedFailed = failed.map(parseFailure)
  if (!parsedPictures.length || parsedPictures.includes(null) || parsedFailed.includes(null)) return null
  return {
    tripId,
    title,
    style: style as Album['style'],
    pictures: parsedPictures as AlbumPicture[],
    failed: parsedFailed as AlbumFailure[],
    createdAt
  }
}

function read(): Album[] {
  try {
    const raw = JSON.parse(localStorage.getItem(ALBUM_LIBRARY_KEY) || 'null')
    if (!isObject(raw) || raw.version !== 1 || !Array.isArray(raw.albums)) return []
    return raw.albums.map(parseAlbum).filter((a): a is Album => a !== null)
  } catch {
    return []
  }
}

function write(albums: Album[]): boolean {
  try {
    localStorage.setItem(ALBUM_LIBRARY_KEY, JSON.stringify({ version: 1, albums }))
    return true
  } catch {
    // Private mode / quota: the album is still on screen, just not kept.
    return false
  }
}

export function loadAlbums(): Album[] {
  return read()
}

export function getAlbum(tripId: string): Album | null {
  return read().find(album => album.tripId === tripId) ?? null
}

/** Newest first, one copy per tripId. Re-reads first so another tab's albums survive. */
export function saveAlbum(album: Album): boolean {
  const others = read().filter(saved => saved.tripId !== album.tripId)
  return write([album, ...others].slice(0, MAX_SAVED_ALBUMS))
}

/** Forgets the album in this browser only; the comic service keeps its copy. */
export function removeAlbum(tripId: string): void {
  write(read().filter(album => album.tripId !== tripId))
}
