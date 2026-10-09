"""
siamese_unet.py - Siamese & Early-Fusion UNet with Pretrained ResNet Encoders.
Implements Feature #1 using segmentation_models_pytorch (SMP).
"""

from typing import Optional
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


class SiameseUNet(nn.Module):
    """
    Siamese / Early-Fusion UNet for multi-spectral and optical change detection.
    Powered by pretrained ResNet encoders via segmentation_models_pytorch.
    """
    def __init__(
        self,
        encoder_name: str = "resnet18",
        encoder_weights: Optional[str] = "imagenet",
        in_channels_per_image: int = 3,
        classes: int = 2,
        mode: str = "early_fusion"  # 'early_fusion' or 'siamese_diff'
    ):
        super(SiameseUNet, self).__init__()
        self.mode = mode
        self.in_channels = in_channels_per_image

        if mode == "early_fusion":
            # Stacked input: (T1, T2) -> 2 * in_channels (e.g. 6 channels for RGB, 8 for RGB+NIR)
            total_in_channels = in_channels_per_image * 2
            self.model = smp.Unet(
                encoder_name=encoder_name,
                encoder_weights=encoder_weights,
                in_channels=total_in_channels,
                classes=classes
            )
        else:
            # Siamese feature difference mode
            self.encoder = smp.encoders.get_encoder(
                encoder_name,
                in_channels=in_channels_per_image,
                depth=5,
                weights=encoder_weights
            )
            # Decoder taking difference features
            decoder_channels = (256, 128, 64, 32, 16)
            self.decoder = smp.decoders.unet.decoder.UnetDecoder(
                encoder_channels=self.encoder.out_channels,
                decoder_channels=decoder_channels,
                n_blocks=5,
                use_norm="batchnorm",
                attention_type=None
            )
            self.segmentation_head = smp.base.SegmentationHead(
                in_channels=decoder_channels[-1],
                out_channels=classes,
                activation=None,
                kernel_size=3
            )

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        if self.mode == "early_fusion":
            x = torch.cat([x1, x2], dim=1)
            return self.model(x)
        else:
            # Siamese feature difference
            feats1 = self.encoder(x1)
            feats2 = self.encoder(x2)
            diff_feats = [torch.abs(f1 - f2) for f1, f2 in zip(feats1, feats2)]
            decoded = self.decoder(diff_feats)
            return self.segmentation_head(decoded)

    def predict_change_prob(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        """Returns normalized change probability in [0, 1]."""
        logits = self.forward(x1, x2)
        prob = torch.softmax(logits, dim=1)[:, 1]
        return prob
