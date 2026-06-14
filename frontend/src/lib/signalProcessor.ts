export interface SignalData {
  time: number[];
  ecg: number[];
  resp: number[];
  headers: string[];
}

export interface AnalysisResults {
  fileName: string;
  duration: number;
  sampleRate: number;
  avgHeartRate: number;
  avgRespRate: number;
  meanRR: number;
  minHR: number;
  maxHR: number;
  sdnn: number;
  rmssd: number;
  pnn50: number;
  rsaMs: number;
  lf: number;
  hf: number;
  lfHf: number;
  lfnu: number;
  hfnu: number;
  totalPower: number;
  respHz: number;
  peaks: number[];
  respPeaks: number[];
  instantaneousHR: { time: number; hr: number }[];
  // Subsampled data for charting
  chartData: { time: number; ecg: number; resp: number; isPeak: boolean }[];
}

/**
 * Parses the BIOPAC CSV file contents.
 */
export function parseCSV(text: string): SignalData {
  const lines = text.split(/\r?\n/);
  if (lines.length < 2) {
    throw new Error("CSV file is empty or invalid");
  }

  // Parse headers
  const headers = lines[0].split(",").map(h => h.trim());
  
  // Find indices
  const timeIdx = headers.findIndex(h => h.toLowerCase() === "sec" || h.toLowerCase() === "time");
  const ecgIdx = headers.findIndex(h => h.toUpperCase() === "CH1" || h.toLowerCase().includes("ecg"));
  const respIdx = headers.findIndex(h => h.toUpperCase() === "CH2" || h.toLowerCase().includes("resp") || h.toLowerCase().includes("rsp"));

  if (timeIdx === -1) {
    throw new Error("Could not find time/sec column in CSV");
  }
  if (ecgIdx === -1) {
    throw new Error("Could not find ECG column (CH1) in CSV");
  }

  const time: number[] = [];
  const ecg: number[] = [];
  const resp: number[] = [];

  // Parse rows (skip header, skip trailing empty lines)
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]) continue;
    const cols = lines[i].split(",");
    if (cols.length <= Math.max(timeIdx, ecgIdx)) continue;

    const t = parseFloat(cols[timeIdx]);
    const e = parseFloat(cols[ecgIdx]);
    const r = respIdx !== -1 && cols[respIdx] ? parseFloat(cols[respIdx]) : 0;

    if (isNaN(t) || isNaN(e)) continue;

    time.push(t);
    ecg.push(e);
    resp.push(isNaN(r) ? 0 : r);
  }

  return { time, ecg, resp, headers };
}

/**
 * Robust R-peak detection in ECG signal
 */
export function findRPeaks(ecg: number[], sampleRate: number): number[] {
  const minDistance = Math.round(0.38 * sampleRate); // Minimum distance between heartbeats (~158 bpm limit)
  
  // Calculate mean and standard deviation
  let sum = 0;
  for (let i = 0; i < ecg.length; i++) sum += ecg[i];
  const mean = sum / ecg.length;

  let sqDiffSum = 0;
  for (let i = 0; i < ecg.length; i++) sqDiffSum += Math.pow(ecg[i] - mean, 2);
  const std = Math.sqrt(sqDiffSum / ecg.length);

  // Dynamic threshold for peak detection (R-peaks are large spikes)
  const threshold = mean + 1.2 * std;

  const peaks: number[] = [];
  let lastPeakIdx = -minDistance;

  for (let i = 1; i < ecg.length - 1; i++) {
    const val = ecg[i];
    // Local maximum
    if (val > ecg[i - 1] && val > ecg[i + 1]) {
      if (val > threshold) {
        if (i - lastPeakIdx >= minDistance) {
          peaks.push(i);
          lastPeakIdx = i;
        } else if (peaks.length > 0 && val > ecg[peaks[peaks.length - 1]]) {
          // If this peak is higher than the previous one in the window, replace it
          peaks[peaks.length - 1] = i;
          lastPeakIdx = i;
        }
      }
    }
  }

  return peaks;
}

/**
 * Respiration peak detection
 */
export function findRespirationPeaks(resp: number[], sampleRate: number): number[] {
  // Smooth the respiration signal with a moving average filter to reduce high frequency noise
  const windowSize = Math.round(sampleRate * 0.8); // 800ms window smoothing
  const smoothed: number[] = new Array(resp.length);
  
  let currentSum = 0;
  for (let i = 0; i < Math.min(windowSize, resp.length); i++) {
    currentSum += resp[i];
  }
  smoothed[0] = currentSum / Math.min(windowSize, resp.length);

  for (let i = 1; i < resp.length; i++) {
    const halfWin = Math.floor(windowSize / 2);
    let start = i - halfWin;
    let end = i + halfWin;
    if (start < 0) start = 0;
    if (end >= resp.length) end = resp.length - 1;
    
    let sum = 0;
    for (let k = start; k <= end; k++) {
      sum += resp[k];
    }
    smoothed[i] = sum / (end - start + 1);
  }

  // Minimum distance between breaths is ~2.2 seconds (max rate of 27 bpm)
  const minDistance = Math.round(2.2 * sampleRate);
  
  let sumSmooth = 0;
  for (let i = 0; i < smoothed.length; i++) sumSmooth += smoothed[i];
  const mean = sumSmooth / smoothed.length;

  const peaks: number[] = [];
  let lastPeakIdx = -minDistance;

  for (let i = 1; i < smoothed.length - 1; i++) {
    if (smoothed[i] > smoothed[i - 1] && smoothed[i] > smoothed[i + 1]) {
      if (smoothed[i] > mean) {
        if (i - lastPeakIdx >= minDistance) {
          peaks.push(i);
          lastPeakIdx = i;
        }
      }
    }
  }

  return peaks;
}

/**
 * Fully analyzes the signal data to calculate HRV, RSA, and average rates
 */
export function analyzeSignals(data: SignalData, fileName: string): AnalysisResults {
  const { time, ecg, resp, headers } = data;
  const totalDuration = time[time.length - 1] - time[0];
  
  const hasRespColumn = headers && headers.some(h => {
    const name = h.toLowerCase();
    return name === "ch2" || name.includes("resp") || name.includes("rsp");
  });

  // Determine sample rate
  const sampleRate = Math.round(1 / (time[1] - time[0]));

  // Detect peaks
  const peaks = findRPeaks(ecg, sampleRate);
  const respPeaks = findRespirationPeaks(resp, sampleRate);

  // Calculate RR intervals (in seconds)
  const rrIntervals: number[] = [];
  const rrTimes: number[] = [];
  for (let i = 1; i < peaks.length; i++) {
    const interval = time[peaks[i]] - time[peaks[i - 1]];
    // Filter outlier RR intervals (keep between 0.3s and 2.0s)
    if (interval >= 0.3 && interval <= 2.0) {
      rrIntervals.push(interval);
      rrTimes.push(time[peaks[i]]);
    }
  }

  // Calculate Heart Rate metrics
  let avgHeartRate = 0;
  let sdnn = 0;
  let rmssd = 0;
  let pnn50 = 0;
  const instantaneousHR: { time: number; hr: number }[] = [];

  if (rrIntervals.length > 0) {
    const sumRR = rrIntervals.reduce((a, b) => a + b, 0);
    const meanRR = sumRR / rrIntervals.length;
    avgHeartRate = 60 / meanRR;

    // SDNN (ms)
    const variance = rrIntervals.reduce((a, b) => a + Math.pow(b - meanRR, 2), 0) / rrIntervals.length;
    sdnn = Math.sqrt(variance) * 1000;

    // RMSSD (ms) and pNN50
    let diffSqSum = 0;
    let nn50Count = 0;
    for (let i = 1; i < rrIntervals.length; i++) {
      const diff = Math.abs(rrIntervals[i] - rrIntervals[i - 1]);
      diffSqSum += Math.pow(diff, 2);
      if (diff > 0.05) {
        nn50Count++;
      }
    }

    if (rrIntervals.length > 1) {
      rmssd = Math.sqrt(diffSqSum / (rrIntervals.length - 1)) * 1000;
      pnn50 = (nn50Count / (rrIntervals.length - 1)) * 1000; // standard representation
      pnn50 = Math.min(100, Math.max(0, (nn50Count / (rrIntervals.length - 1)) * 100));
    }

    // Instantaneous heart rate mapping
    for (let i = 0; i < rrIntervals.length; i++) {
      instantaneousHR.push({
        time: rrTimes[i],
        hr: 60 / rrIntervals[i],
      });
    }
  }

  // Calculate extra time-domain HRV stats
  const meanRR = rrIntervals.length > 0 ? (rrIntervals.reduce((a, b) => a + b, 0) / rrIntervals.length) * 1000 : 0;
  const minHR = instantaneousHR.length > 0 ? Math.min(...instantaneousHR.map(pt => pt.hr)) : 0;
  const maxHR = instantaneousHR.length > 0 ? Math.max(...instantaneousHR.map(pt => pt.hr)) : 0;

  // Calculate Respiration Rate
  let avgRespRate = 0;
  let respHz = 0;
  if (hasRespColumn && respPeaks.length > 1) {
    const breathIntervals: number[] = [];
    for (let i = 1; i < respPeaks.length; i++) {
      breathIntervals.push(time[respPeaks[i]] - time[respPeaks[i - 1]]);
    }
    const meanBreathInterval = breathIntervals.reduce((a, b) => a + b, 0) / breathIntervals.length;
    avgRespRate = 60 / meanBreathInterval;
    respHz = 1 / meanBreathInterval;
  }

  // Calculate Respiratory Sinus Arrhythmia (RSA) in ms
  // Find min and max RR intervals in each breath cycle (peak to peak)
  let rsaMs = 0;
  const cycleRsaValues: number[] = [];

  if (respPeaks.length > 1 && rrIntervals.length > 2) {
    for (let i = 0; i < respPeaks.length - 1; i++) {
      const tStart = time[respPeaks[i]];
      const tEnd = time[respPeaks[i + 1]];

      // Find RR intervals inside this breath cycle
      const cycleRRs = rrIntervals.filter((_, idx) => {
        const t = rrTimes[idx];
        return t >= tStart && t < tEnd;
      });

      if (cycleRRs.length >= 2) {
        const minRR = Math.min(...cycleRRs);
        const maxRR = Math.max(...cycleRRs);
        cycleRsaValues.push((maxRR - minRR) * 1000);
      }
    }

    if (cycleRsaValues.length > 0) {
      rsaMs = cycleRsaValues.reduce((a, b) => a + b, 0) / cycleRsaValues.length;
    }
  }

  // Subsample signals for UI charting to prevent DOM lag (target ~1500 points total)
  const targetPoints = 1500;
  const step = Math.max(1, Math.floor(ecg.length / targetPoints));
  
  const chartData: { time: number; ecg: number; resp: number; isPeak: boolean }[] = [];
  const peakSet = new Set(peaks);

  for (let i = 0; i < ecg.length; i += step) {
    // Check if there's any R-peak in the skipped segment to preserve visual peaks
    let isPeak = false;
    for (let j = 0; j < step && i + j < ecg.length; j++) {
      if (peakSet.has(i + j)) {
        isPeak = true;
        break;
      }
    }

    chartData.push({
      time: time[i],
      ecg: ecg[i],
      resp: resp[i],
      isPeak,
    });
  }

  return {
    fileName,
    duration: totalDuration,
    sampleRate,
    avgHeartRate: Math.round(avgHeartRate * 10) / 10,
    avgRespRate: Math.round(avgRespRate * 10) / 10,
    meanRR: Math.round(meanRR * 10) / 10,
    minHR: Math.round(minHR * 10) / 10,
    maxHR: Math.round(maxHR * 10) / 10,
    sdnn: Math.round(sdnn * 10) / 10,
    rmssd: Math.round(rmssd * 10) / 10,
    pnn50: Math.round(pnn50 * 10) / 10,
    rsaMs: Math.round(rsaMs * 10) / 10,
    lf: 0,
    hf: 0,
    lfHf: 0,
    lfnu: 0,
    hfnu: 0,
    totalPower: 0,
    respHz,
    peaks,
    respPeaks,
    instantaneousHR,
    chartData,
  };
}

/**
 * Generates synthetic ECG and respiration signals with RSA for demo purposes
 */
export function generateSyntheticData(): SignalData {
  const sampleRate = 250;
  const duration = 60; // 60 seconds
  const totalSamples = sampleRate * duration;
  
  const time: number[] = [];
  const ecg: number[] = [];
  const resp: number[] = [];
  
  // Respiration frequency: 12 breaths/min = 0.2 Hz
  const respFreq = 0.2;
  
  // Heart rate baseline: 72 bpm. Modulate by respiration (amplitude of 6 bpm)
  const baseHr = 72;
  const hrvAmp = 6; 
  
  // Generate signals sample by sample
  for (let s = 0; s < totalSamples; s++) {
    const t = s / sampleRate;
    time.push(t);
    
    // Respiration signal: slow sine wave with some small high frequency noise
    const rVal = Math.sin(2 * Math.PI * respFreq * t) + 0.05 * Math.sin(2 * Math.PI * 8 * t);
    resp.push(rVal);
  }
  
  // Generate ECG beats with RSA modulation
  const beats: number[] = [];
  let tCursor = 0;
  
  while (tCursor < duration) {
    beats.push(tCursor);
    // Modulate heart rate: faster during inspiration (respVal > 0), slower during expiration
    const respVal = Math.sin(2 * Math.PI * respFreq * tCursor);
    const instantaneousHr = baseHr + hrvAmp * respVal + (Math.random() - 0.5) * 2.5; // add some random variation
    const nextInterval = 60 / instantaneousHr;
    tCursor += nextInterval;
  }
  
  // Create ECG signal based on beats
  // Initialize with some base baseline wander and muscle noise
  for (let s = 0; s < totalSamples; s++) {
    const t = s / sampleRate;
    const wander = 0.15 * Math.sin(2 * Math.PI * 0.1 * t);
    const noise = 0.02 * (Math.random() - 0.5);
    ecg.push(wander + noise);
  }
  
  // Add QRS complex for each heartbeat
  beats.forEach(beatTime => {
    const beatSample = Math.round(beatTime * sampleRate);
    
    // QRS template: P-wave, QRS spike, T-wave
    // P wave: small bump 120ms before R peak
    const pOffset = Math.round(-0.12 * sampleRate);
    const pWidth = Math.round(0.04 * sampleRate);
    for (let w = -pWidth; w <= pWidth; w++) {
      const idx = beatSample + pOffset + w;
      if (idx >= 0 && idx < totalSamples) {
        const factor = 1 - Math.pow(w / pWidth, 2);
        ecg[idx] += 0.1 * factor;
      }
    }
    
    // QRS complex: sharp down-up-down spike within 60ms around R-peak
    const qOffset = Math.round(-0.02 * sampleRate);
    const sOffset = Math.round(0.02 * sampleRate);
    
    // Q: small negative
    if (beatSample + qOffset >= 0 && beatSample + qOffset < totalSamples) {
      ecg[beatSample + qOffset] -= 0.15;
    }
    
    // R: large positive
    const rWidth = Math.round(0.015 * sampleRate);
    for (let w = -rWidth; w <= rWidth; w++) {
      const idx = beatSample + w;
      if (idx >= 0 && idx < totalSamples) {
        const factor = 1 - Math.pow(w / rWidth, 2);
        ecg[idx] += 1.5 * factor;
      }
    }
    
    // S: medium negative
    if (beatSample + sOffset >= 0 && beatSample + sOffset < totalSamples) {
      ecg[beatSample + sOffset] -= 0.25;
    }
    
    // T wave: wider bump 250ms after R peak
    const tOffset = Math.round(0.24 * sampleRate);
    const tWidth = Math.round(0.06 * sampleRate);
    for (let w = -tWidth; w <= tWidth; w++) {
      const idx = beatSample + tOffset + w;
      if (idx >= 0 && idx < totalSamples) {
        const factor = 1 - Math.pow(w / tWidth, 2);
        ecg[idx] += 0.25 * factor;
      }
    }
  });
  
  return { time, ecg, resp, headers: ["sec", "CH1", "CH2"] };
}

