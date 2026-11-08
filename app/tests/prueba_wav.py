import sys, time, os
import onnx_asr
model_dir, wav = sys.argv[1], sys.argv[2]
t0 = time.perf_counter()
m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", model_dir, quantization="int8")
t1 = time.perf_counter()
txt = m.recognize(wav)
t2 = time.perf_counter()
txt = m.recognize(wav)
t3 = time.perf_counter()
print(f"carga={t1-t0:.2f}s  1a_transcripcion={t2-t1:.2f}s  2a_transcripcion={t3-t2:.2f}s")
print("TEXTO:", txt)
