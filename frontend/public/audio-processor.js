class VocalFluxAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunks = [];
    this.sampleCount = 0;
    this.chunkSize = 2048;
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input?.[0];
    if (channel && channel.length > 0) {
      this.chunks.push(new Float32Array(channel));
      this.sampleCount += channel.length;
    }
    if (this.sampleCount >= this.chunkSize) {
      const output = new Float32Array(this.sampleCount);
      let offset = 0;
      for (const chunk of this.chunks) {
        output.set(chunk, offset);
        offset += chunk.length;
      }
      this.port.postMessage(output, [output.buffer]);
      this.chunks = [];
      this.sampleCount = 0;
    }
    return true;
  }
}

registerProcessor("vocalflux-audio-processor", VocalFluxAudioProcessor);
