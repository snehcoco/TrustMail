"""
ONNX Export Script
==================
Exports a fine-tuned HuggingFace transformer model to ONNX format.

Also runs:
  - ONNX model verification (matches PyTorch outputs)
  - Optional quantization (INT8 for faster CPU inference)

Usage:
    python training/export_onnx.py \
        --model-dir trained_models/transformer_finetuned \
        --output trained_models/distilbert_phishing.onnx \
        --quantize
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))


def export_to_onnx(model_dir: str, output_path: str, opset_version: int = 14) -> None:
    """
    Export a PyTorch transformer model to ONNX.

    Args:
        model_dir: Directory containing the saved HuggingFace model.
        output_path: Output path for the ONNX file.
        opset_version: ONNX opset version (14+ recommended).
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    logger.info(f"Loading model from {model_dir}")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True)
    model.eval()

    # Create dummy inputs
    dummy_text = "Your account has been suspended. Click here to verify."
    dummy_inputs = tokenizer(
        dummy_text,
        return_tensors="pt",
        max_length=512,
        padding="max_length",
        truncation=True,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting to ONNX (opset {opset_version})...")

    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_inputs["input_ids"], dummy_inputs["attention_mask"]),
            str(output_path),
            opset_version=opset_version,
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "logits": {0: "batch_size"},
            },
            do_constant_folding=True,
        )

    logger.info(f"✓ ONNX model exported: {output_path}")

    # ── Verify ONNX output matches PyTorch ──────────────────────────────────
    verify_export(model, dummy_inputs, str(output_path))


def verify_export(pytorch_model, dummy_inputs: dict, onnx_path: str) -> None:
    """Verify ONNX model produces outputs close to PyTorch model."""
    import torch
    import onnxruntime as ort

    logger.info("Verifying ONNX export...")

    # PyTorch output
    with torch.no_grad():
        pt_outputs = pytorch_model(**dummy_inputs)
        pt_logits = pt_outputs.logits.numpy()

    # ONNX Runtime output
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    ort_inputs = {
        "input_ids": dummy_inputs["input_ids"].numpy().astype(np.int64),
        "attention_mask": dummy_inputs["attention_mask"].numpy().astype(np.int64),
    }
    ort_outputs = sess.run(["logits"], ort_inputs)
    ort_logits = ort_outputs[0]

    max_diff = np.max(np.abs(pt_logits - ort_logits))
    logger.info(f"Max output difference PyTorch vs ONNX: {max_diff:.6f}")

    if max_diff > 1e-3:
        logger.warning(f"Larger-than-expected difference: {max_diff:.6f}")
    else:
        logger.info("✓ ONNX verification passed")


def quantize_onnx(input_path: str, output_path: str) -> None:
    """
    Apply dynamic INT8 quantization to the ONNX model.
    Reduces model size by ~4x with minimal accuracy loss on CPU.
    """
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType

        logger.info(f"Quantizing {input_path} -> {output_path}")
        quantize_dynamic(
            model_input=input_path,
            model_output=output_path,
            weight_type=QuantType.QInt8,
        )
        logger.info(f"✓ Quantized model saved: {output_path}")

        # Report size reduction
        orig_size = Path(input_path).stat().st_size / (1024 * 1024)
        quant_size = Path(output_path).stat().st_size / (1024 * 1024)
        logger.info(f"Size: {orig_size:.1f} MB -> {quant_size:.1f} MB ({quant_size/orig_size*100:.0f}%)")

    except ImportError:
        logger.error("onnxruntime-tools not installed. pip install onnxruntime-tools")


def main():
    parser = argparse.ArgumentParser(description="Export TrustMail model to ONNX")
    parser.add_argument("--model-dir", required=True, help="HuggingFace model directory")
    parser.add_argument("--output", required=True, help="Output ONNX path")
    parser.add_argument("--quantize", action="store_true", help="Apply INT8 quantization")
    parser.add_argument("--opset", type=int, default=14)
    args = parser.parse_args()

    export_to_onnx(args.model_dir, args.output, args.opset)

    if args.quantize:
        quant_path = args.output.replace(".onnx", "_quantized.onnx")
        quantize_onnx(args.output, quant_path)


if __name__ == "__main__":
    main()
