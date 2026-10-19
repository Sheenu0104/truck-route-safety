import L from 'leaflet';
import { useEffect, useMemo, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { blendFrames, buildFrames } from '../../lib/heatmap';
import type { HeatMetric, HeatmapResponse } from '../../types';

const PANE = 'heat';

interface Props {
  data: HeatmapResponse;
  metric: HeatMetric;
  hour: number;
  opacity?: number;
}

/**
 * The corridor grid is drawn into a tiny canvas (one pixel per forecast cell)
 * that Leaflet stretches over the grid bounds. The browser's bilinear scaling
 * turns the cells into a smooth heatmap for free, and scrubbing the slider only
 * rewrites a few thousand bytes of pixels, so it stays at 60 fps.
 */
export function HeatmapOverlay({ data, metric, hour, opacity = 1 }: Props) {
  const map = useMap();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const layerRef = useRef<L.SVGOverlay | null>(null);
  const frames = useMemo(() => buildFrames(data, metric), [data, metric]);

  // Create the overlay once per data set.
  useEffect(() => {
    if (!map.getPane(PANE)) {
      const pane = map.createPane(PANE);
      pane.style.zIndex = '350'; // above tiles (200), below routes (400)
      pane.style.pointerEvents = 'none';
    }
    const canvas = document.createElement('canvas');
    canvas.width = data.cols;
    canvas.height = data.rows;
    canvas.className = 'heat-canvas';
    const { south, west, north, east } = data.bounds;
    // svgOverlay only positions and scales the element it is given, so it works for a canvas too.
    const layer = L.svgOverlay(canvas as unknown as SVGElement, [[south, west], [north, east]], {
      pane: PANE,
      interactive: false,
    }).addTo(map);
    canvasRef.current = canvas;
    layerRef.current = layer;
    return () => {
      layer.remove();
      canvasRef.current = null;
      layerRef.current = null;
    };
  }, [map, data]);

  useEffect(() => {
    layerRef.current?.setOpacity(opacity);
  }, [opacity]);

  // Repaint on every slider move.
  const imageRef = useRef<ImageData | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || frames.length === 0) return;
    if (!imageRef.current || imageRef.current.width !== canvas.width || imageRef.current.height !== canvas.height) {
      imageRef.current = ctx.createImageData(canvas.width, canvas.height);
    }
    blendFrames(frames, hour, imageRef.current.data);
    ctx.putImageData(imageRef.current, 0, 0);
  }, [frames, hour, data]);

  return null;
}
