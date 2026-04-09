# MNIST Digit Classification — Project Brief

## Objective

Build a simple digit classifier that recognizes handwritten digits (0-9) from the MNIST dataset. This is a toy project to validate the Zero Operators pipeline end-to-end.

## Data

- **MNIST dataset** — 70,000 28x28 grayscale images of handwritten digits
- **Training set**: 60,000 images
- **Test set**: 10,000 images
- Available via `torchvision.datasets.MNIST`

## Success Criteria

- Test accuracy > 95%
- Model trains in under 5 minutes on CPU
- Inference latency < 10ms per image

## Requirements

- PyTorch for model training
- Simple CNN architecture (no pre-trained models needed for MNIST)
- Include confusion matrix in validation report
- Reproducible with fixed random seed
