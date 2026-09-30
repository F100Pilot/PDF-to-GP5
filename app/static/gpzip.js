"use strict";

// A .gp (Guitar Pro 7/8) is a ZIP. alphaTab's exporter stores the audio track as
// "Content/Assets/backing-track", with no extension; Guitar Pro and Songsterr files name it
// with one ("….mp3"), and a program that goes by the extension misses the audio. This renames
// it to "backing-track.<ext>" (from the audio's first bytes) and points score.gpif's
// <EmbeddedFilePath> at the new name. The audio's compressed bytes are copied as they are;
// only score.gpif is inflated, edited and deflated again (the browser's own
// DecompressionStream / CompressionStream). Anything unexpected returns the file unchanged.
(() => {
  const OLD_NAME = "Content/Assets/backing-track";
  const GPIF = "Content/score.gpif";
  const LOCAL = 0x04034b50;
  const CENTRAL = 0x02014b50;
  const END = 0x06054b50;
  const DEFLATE = 8;

  function audioExtension(bytes) {
    const ascii = (from, to) => String.fromCharCode(...bytes.subarray(from, to));
    if (ascii(0, 3) === "ID3" || (bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0)) return "mp3";
    if (ascii(0, 4) === "OggS") return "ogg";
    if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WAVE") return "wav";
    return null;
  }

  let crcTable = null;
  function crc32(bytes) {
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        crcTable[n] = c >>> 0;
      }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  async function pipe(bytes, stream) {
    const buffer = await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer();
    return new Uint8Array(buffer);
  }

  // The entries of a ZIP without data descriptors or ZIP64 (what alphaTab writes).
  function readEntries(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let end = bytes.length - 22;
    while (end >= 0 && view.getUint32(end, true) !== END) end--;
    if (end < 0) throw new Error("not a ZIP");
    const count = view.getUint16(end + 10, true);
    let at = view.getUint32(end + 16, true);
    const decoder = new TextDecoder();
    const entries = [];
    for (let i = 0; i < count; i++) {
      if (view.getUint32(at, true) !== CENTRAL) throw new Error("bad central directory");
      const nameLength = view.getUint16(at + 28, true);
      const extraLength = view.getUint16(at + 30, true);
      const commentLength = view.getUint16(at + 32, true);
      const local = view.getUint32(at + 42, true);
      if (view.getUint32(local, true) !== LOCAL) throw new Error("bad local header");
      const dataStart = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
      const compressedSize = view.getUint32(at + 20, true);
      entries.push({
        name: decoder.decode(bytes.subarray(at + 46, at + 46 + nameLength)),
        method: view.getUint16(at + 10, true),
        time: view.getUint16(at + 12, true),
        date: view.getUint16(at + 14, true),
        crc: view.getUint32(at + 16, true),
        size: view.getUint32(at + 24, true),
        data: bytes.subarray(dataStart, dataStart + compressedSize),
      });
      at += 46 + nameLength + extraLength + commentLength;
    }
    return entries;
  }

  function writeEntries(entries) {
    const encoder = new TextEncoder();
    const names = entries.map((e) => encoder.encode(e.name));
    const localSize = entries.reduce((sum, e, i) => sum + 30 + names[i].length + e.data.length, 0);
    const centralSize = entries.reduce((sum, e, i) => sum + 46 + names[i].length, 0);
    const out = new Uint8Array(localSize + centralSize + 22);
    const view = new DataView(out.buffer);
    const offsets = [];
    let at = 0;
    const header = (signature, e, name, extraFields) => {
      view.setUint32(at, signature, true);
      let p = at + 4;
      if (signature === CENTRAL) { view.setUint16(p, 20, true); p += 2; } // version made by
      view.setUint16(p, 20, true); // version needed
      view.setUint16(p + 2, 0x0800, true); // UTF-8 names
      view.setUint16(p + 4, e.method, true);
      view.setUint16(p + 6, e.time, true);
      view.setUint16(p + 8, e.date, true);
      view.setUint32(p + 10, e.crc, true);
      view.setUint32(p + 14, e.data.length, true);
      view.setUint32(p + 18, e.size, true);
      view.setUint16(p + 22, name.length, true);
      view.setUint16(p + 24, 0, true); // extra field length
      p += 26;
      p = extraFields(p);
      out.set(name, p);
      return p + name.length;
    };
    entries.forEach((e, i) => {
      offsets.push(at);
      at = header(LOCAL, e, names[i], (p) => p);
      out.set(e.data, at);
      at += e.data.length;
    });
    const centralStart = at;
    entries.forEach((e, i) => {
      at = header(CENTRAL, e, names[i], (p) => {
        view.setUint16(p, 0, true); // comment length
        view.setUint16(p + 2, 0, true); // disk number
        view.setUint16(p + 4, 0, true); // internal attributes
        view.setUint32(p + 6, 0, true); // external attributes
        view.setUint32(p + 10, offsets[i], true);
        return p + 14;
      });
    });
    view.setUint32(at, END, true);
    view.setUint16(at + 8, entries.length, true);
    view.setUint16(at + 10, entries.length, true);
    view.setUint32(at + 12, at - centralStart, true);
    view.setUint32(at + 16, centralStart, true);
    return out;
  }

  async function nameBackingTrack(gp, audio) {
    const extension = audioExtension(audio);
    if (!extension || typeof DecompressionStream !== "function" || typeof CompressionStream !== "function") return gp;
    try {
      const entries = readEntries(gp);
      const asset = entries.find((e) => e.name === OLD_NAME);
      const gpif = entries.find((e) => e.name === GPIF);
      if (!asset || !gpif || gpif.method !== DEFLATE) return gp;
      const newName = `${OLD_NAME}.${extension}`;
      const xml = new TextDecoder().decode(await pipe(gpif.data, new DecompressionStream("deflate-raw")));
      const target = `<![CDATA[${OLD_NAME}]]>`;
      if (!xml.includes(target)) return gp;
      const edited = new TextEncoder().encode(xml.split(target).join(`<![CDATA[${newName}]]>`));
      gpif.data = await pipe(edited, new CompressionStream("deflate-raw"));
      gpif.crc = crc32(edited);
      gpif.size = edited.length;
      asset.name = newName;
      return writeEntries(entries);
    } catch {
      return gp; // an export alphaTab changed: keep its file as it is
    }
  }

  window.GpZip = { nameBackingTrack, audioExtension };
})();
