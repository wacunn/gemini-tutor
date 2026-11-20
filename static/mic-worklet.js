// Captures mic audio, downsamples to 16 kHz mono PCM16, posts 40 ms frames + a level reading.
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.acc = 0;
    this.sum = 0;
    this.n = 0;
    this.frame = new Int16Array(640);
    this.idx = 0;
    this.levelSum = 0;
    this.levelN = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const v = ch[i];
      this.sum += v;
      this.n += 1;
      this.levelSum += v * v;
      this.levelN += 1;
      this.acc += 1;
      if (this.acc >= this.ratio) {
        this.acc -= this.ratio;
        let s = this.sum / this.n;
        this.sum = 0;
        this.n = 0;
        s = Math.max(-1, Math.min(1, s));
        this.frame[this.idx++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.idx === this.frame.length) {
          const level = Math.sqrt(this.levelSum / Math.max(1, this.levelN));
          this.levelSum = 0;
          this.levelN = 0;
          this.port.postMessage({ pcm: this.frame.buffer.slice(0), level });
          this.idx = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);
