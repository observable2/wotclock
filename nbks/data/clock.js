// wotclock logic, ported from the 'mainspring' wired sprite track of clock.mov (QuickTime 6.5, 2005).
// The original script is a single idle handler; `createMainspring` below is that handler.
// Stage and layer geometry come from the track headers of clock.mov.

// Stage of the original movie: pauls (780x120) above scene/whisper (780x410).
export const STAGE = { width: 780, height: 530, pauls: { x: 0, y: 0, w: 780, h: 120 }, scene: { x: 0, y: 120, w: 780, h: 410 } };

// Pan angle (degrees) at which the St Paul's panorama shows the numeral for hour 0..23 under the centre mark.
// Straight from the sprite variables 2004..2027.
export const HOUR_PAN = [340, 326.5, 315, 305, 294, 281.5, 267, 249, 232, 215, 199, 181, 164, 145, 130, 114, 96, 80, 62, 49, 35, 21, 8, 353];

// 'pauls' is panned to an approximate analogue reading of the time: between this hour's angle and the next one's.
export function analogPan(hour, minute) {
  const next = (hour + 1) % 24;
  let span = HOUR_PAN[hour] - HOUR_PAN[next];
  if (span < 0) span += 360;
  let pan = HOUR_PAN[hour] - (minute * span) / 60;
  if (pan < 0) pan += 360;
  return pan;
}

// The letter dial ('clockface'): the stage is 780 wide, the dial is a 480x400 track at (190,124); each cell is 40x40.
// e=1 t=2 a=3 n=4 i=5 o=6 s=7 l=8 r=9; one cell per hand position, clockwise from 12.
export const DIAL = {
  x: 190, y: 124, w: 480, h: 400, cell: 40,
  cells: [
    { at: 12, x: 184, y: 0, text: "ET" },
    { at: 1, x: 284, y: 29, text: "E" },
    { at: 2, x: 346, y: 89, text: "T" },
    { at: 3, x: 362, y: 183, text: "A" },
    { at: 4, x: 345, y: 270, text: "N" },
    { at: 5, x: 283, y: 329, text: "I" },
    { at: 6, x: 183, y: 360, text: "O" },
    { at: 7, x: 86, y: 330, text: "S" },
    { at: 8, x: 23, y: 271, text: "L" },
    { at: 9, x: 0, y: 184, text: "R" },
    { at: 10, x: 24, y: 90, text: "E…" },
    { at: 11, x: 87, y: 30, text: "EE" },
  ],
};

// The 'clockface' text tracks turn each letter red for 5 s in turn, once round per minute.
export const dialIndex = (second) => Math.floor(second / 5) % 12;

// The 'clockhands' text track (hnds/cHHhands.txt, one file per hour, hour 0 uses c24) holds a phrase for every 4 s of
// the hour, selected by minute*60+second. Red letters are wrapped in {} in hands.json.
export const HANDS = { x: 215, y: 272, w: 430, h: 96 };
export const handsFile = (hour) => (hour === 0 ? 24 : hour) - 1; // index into hands.json
export const handsEntry = (minute, second) => Math.floor((minute * 60 + second) / 4);

// Node ids in the QTVR movies: whisperscene.mov has nodes 1..24, clockscene.mov nodes 25..48 (hour 0 -> 24 / 48).
// Here both are 0-based indexes into panos.json.
export const nodeIndex = (hour) => (hour === 0 ? 24 : hour) - 1;

// Both scene movies keep turning slowly: each idle event adds 0.05 degrees to the pan angle.
export const IDLE_DEGREES = 0.05;
// The idle rate is not recorded in the movie; QuickTime idles a track many times a second. This sets 1.5 degrees/s.
export const IDLE_HZ = 30;

// Port of the idle handler. `act` supplies the effects:
//   act.loadScenes(hour)        select the scene and whisper nodes (and clockhands file) for this hour
//   act.preload(hour)           (optional) fetch the next hour's panoramas ahead of time
//   act.setPauls(pan)           pan the St Paul's panorama
//   act.restartFace()           clockface back to time 0 (the dial hand starts again)
//   act.setLayers(scene, whisper)  QuickTime layers: lower is in front; scene starts at 5, whisper at 9
export function createMainspring({ act, random = Math.random }) {
  let minute = -1; // variable 2000
  let hour = -1; // variable 2003
  let sceneFront = true; // variable 2002 (1: scene in front)
  let layers = { scene: 5, whisper: 9 };
  let preloaded = -1;

  const setLayers = (scene, whisper) => {
    layers = { scene, whisper };
    act.setLayers(scene, whisper);
  };

  return {
    get layers() {
      return layers;
    },
    // The 'else' branch of the handler: the first idle, before variable 2001 is set.
    async init(now) {
      sceneFront = true;
      minute = now.getMinutes();
      hour = now.getHours();
      await act.loadScenes(hour);
      act.setPauls(HOUR_PAN[hour]);
    },
    // Every idle after that.
    tick(now) {
      const h = now.getHours();
      const m = now.getMinutes();
      const s = now.getSeconds();
      act.setPauls(analogPan(h, m));
      act.showHands(h, m, s);
      if (m === 59 && s >= 30 && preloaded !== h) {
        preloaded = h;
        act.preload?.((h + 1) % 24); // not in the original, which streamed the next nodes on demand
      }
      if (minute !== m) {
        act.restartFace();
        minute = m;
        if (sceneFront) {
          // on the minute, sometimes the scene shifts to reveal the underlying imaginary (random 1..2 == 1)
          if (random() < 0.5) {
            setLayers(9, -9);
            sceneFront = false;
          }
        } else {
          setLayers(-9, 9);
          sceneFront = true;
        }
      }
      if (hour !== h) {
        hour = h;
        act.loadScenes(h);
        sceneFront = false;
      }
    },
  };
}

// {x} marks a red letter in a phrase line.
export const redToHTML = (line) =>
  line.replace(/[&<]/g, (c) => ({ "&": "&amp;", "<": "&lt;" })[c]).replace(/\{(.*?)\}/g, '<span class="red">$1</span>');
