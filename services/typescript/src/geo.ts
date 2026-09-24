/** Small, dependency-free geometry helpers (docs/03-link-service.md §3.4). */
import { isNumber, isObject } from "./json.js";

export const EARTH_RADIUS_M = 6_371_008.8;

export type LatLng = readonly [lat: number, lng: number];

export const roundHalfUp = (value: number): number => Math.floor(value + 0.5);
export const round6 = (value: number): number => Math.floor(value * 1_000_000 + 0.5) / 1_000_000;

const rad = (deg: number) => (deg * Math.PI) / 180;

export function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const dp = rad(lat2 - lat1);
  const dl = rad(lng2 - lng1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

function isPosition(p: unknown): p is number[] {
  return Array.isArray(p) && p.length >= 2 && isNumber(p[0]) && isNumber(p[1]);
}

function positions(geometry: unknown): number[][] {
  if (!isObject(geometry)) throw new Error("geometry is not an object");
  const { type, coordinates } = geometry;
  let points: unknown;
  if (type === "Point") points = [coordinates];
  else if (type === "LineString") points = coordinates;
  else if (type === "Polygon") {
    if (!Array.isArray(coordinates) || !Array.isArray(coordinates[0])) throw new Error("polygon has no rings");
    const ring = coordinates[0] as unknown[];
    const closed = ring.length > 1 && JSON.stringify(ring[0]) === JSON.stringify(ring[ring.length - 1]);
    points = closed ? ring.slice(0, -1) : ring;
  } else throw new Error(`unsupported geometry type ${JSON.stringify(type)}`);
  if (!Array.isArray(points) || points.length === 0) throw new Error("geometry has no positions");
  if (!points.every(isPosition)) throw new Error("invalid position");
  return points;
}

/** Mean vertex of a GeoJSON Point/LineString/Polygon as [lat, lng], rounded to 6 dp. */
export function centroid(geometry: unknown): LatLng {
  const points = positions(geometry);
  const lng = points.reduce((sum, p) => sum + (p[0] as number), 0) / points.length;
  const lat = points.reduce((sum, p) => sum + (p[1] as number), 0) / points.length;
  return [round6(lat), round6(lng)];
}

/** [lat, lng] of the first APDS PointLocation in a list, or null. */
export function pointOf(location: unknown): LatLng | null {
  if (!Array.isArray(location) || location.length === 0) return null;
  const first = location[0];
  if (!isObject(first) || first.type !== "Point" || !isPosition(first.coordinates)) return null;
  const coords = first.coordinates as number[];
  return [coords[1] as number, coords[0] as number];
}
