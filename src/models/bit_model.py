"""
bit_model.py - Bitemporal Image Transformer (BIT) Change Detection Network.
Implements ResNet-18 backbone + Tokenizer + Transformer Encoder/Decoder + Feature Differencing.
Directly loads our 94.7% accuracy pretrained checkpoint (BIT_LEVIR_best.pt).
"""

import os
from typing import Optional
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange

from src.models.bit.resnet import resnet18, resnet34, resnet50
from src.models.bit.help_funcs import Transformer, TransformerDecoder, TwoLayerConv2d


class ResNetEncoderWrapper(nn.Module):
    """ResNet feature extractor and multi-scale upsampling head for BIT."""
    def __init__(
        self,
        input_nc: int = 3,
        output_nc: int = 2,
        resnet_stages_num: int = 5,
        backbone: str = "resnet18",
        output_sigmoid: bool = False,
        if_upsample_2x: bool = True
    ):
        super(ResNetEncoderWrapper, self).__init__()
        expand = 1
        if backbone == "resnet18":
            self.resnet = resnet18(pretrained=False, replace_stride_with_dilation=[False, True, True])
        elif backbone == "resnet34":
            self.resnet = resnet34(pretrained=False, replace_stride_with_dilation=[False, True, True])
        elif backbone == "resnet50":
            self.resnet = resnet50(pretrained=False, replace_stride_with_dilation=[False, True, True])
            expand = 4
        else:
            raise NotImplementedError(f"Backbone {backbone} not supported")

        self.relu = nn.ReLU()
        self.upsamplex2 = nn.Upsample(scale_factor=2)
        self.upsamplex4 = nn.Upsample(scale_factor=4, mode="bilinear", align_corners=True)
        self.classifier = TwoLayerConv2d(in_channels=32, out_channels=output_nc)

        self.resnet_stages_num = resnet_stages_num
        self.if_upsample_2x = if_upsample_2x
        if self.resnet_stages_num == 5:
            layers = 512 * expand
        elif self.resnet_stages_num == 4:
            layers = 256 * expand
        elif self.resnet_stages_num == 3:
            layers = 128 * expand
        else:
            raise NotImplementedError

        self.conv_pred = nn.Conv2d(layers, 32, kernel_size=3, padding=1)
        self.output_sigmoid = output_sigmoid
        self.sigmoid = nn.Sigmoid()

    def forward_single(self, x: torch.Tensor) -> torch.Tensor:
        x = self.resnet.conv1(x)
        x = self.resnet.bn1(x)
        x = self.resnet.relu(x)
        x = self.resnet.maxpool(x)

        x_4 = self.resnet.layer1(x)
        x_8 = self.resnet.layer2(x_4)

        if self.resnet_stages_num > 3:
            x_8 = self.resnet.layer3(x_8)
        if self.resnet_stages_num == 5:
            x_8 = self.resnet.layer4(x_8)

        if self.if_upsample_2x:
            x = self.upsamplex2(x_8)
        else:
            x = x_8
        x = self.conv_pred(x)
        return x


class BitemporalTransformer(ResNetEncoderWrapper):
    """
    Bitemporal Image Transformer (BIT) for Building & Structural Change Detection.
    Pretrained on LEVIR-CD benchmark (94.7% accuracy).
    """
    def __init__(
        self,
        input_nc: int = 3,
        output_nc: int = 2,
        with_pos: str = "learned",
        resnet_stages_num: int = 5,
        token_len: int = 4,
        token_trans: bool = True,
        enc_depth: int = 1,
        dec_depth: int = 8,
        dim_head: int = 64,
        decoder_dim_head: int = 64,
        tokenizer: bool = True,
        if_upsample_2x: bool = True,
        pool_mode: str = "max",
        pool_size: int = 2,
        backbone: str = "resnet18",
        decoder_softmax: bool = True,
        with_decoder_pos: Optional[str] = None,
        with_decoder: bool = True,
        output_sigmoid: bool = False
    ):
        super(BitemporalTransformer, self).__init__(
            input_nc=input_nc,
            output_nc=output_nc,
            resnet_stages_num=resnet_stages_num,
            backbone=backbone,
            output_sigmoid=output_sigmoid,
            if_upsample_2x=if_upsample_2x
        )
        self.token_len = token_len
        self.conv_a = nn.Conv2d(32, self.token_len, kernel_size=1, padding=0, bias=False)
        self.tokenizer = tokenizer
        if not self.tokenizer:
            self.pooling_size = pool_size
            self.pool_mode = pool_mode
            self.token_len = self.pooling_size * self.pooling_size

        self.token_trans = token_trans
        self.with_decoder = with_decoder
        dim = 32
        mlp_dim = 2 * dim

        self.with_pos = with_pos
        if with_pos == "learned":
            self.pos_embedding = nn.Parameter(torch.randn(1, self.token_len * 2, 32))

        decoder_pos_size = 256 // 4
        self.with_decoder_pos = with_decoder_pos
        if self.with_decoder_pos == "learned":
            self.pos_embedding_decoder = nn.Parameter(
                torch.randn(1, 32, decoder_pos_size, decoder_pos_size)
            )

        self.enc_depth = enc_depth
        self.dec_depth = dec_depth
        self.dim_head = dim_head
        self.decoder_dim_head = decoder_dim_head

        self.transformer = Transformer(
            dim=dim,
            depth=self.enc_depth,
            heads=8,
            dim_head=self.dim_head,
            mlp_dim=mlp_dim,
            dropout=0
        )
        self.transformer_decoder = TransformerDecoder(
            dim=dim,
            depth=self.dec_depth,
            heads=8,
            dim_head=self.decoder_dim_head,
            mlp_dim=mlp_dim,
            dropout=0,
            softmax=decoder_softmax
        )

    def _forward_semantic_tokens(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        spatial_attention = self.conv_a(x)
        spatial_attention = spatial_attention.view([b, self.token_len, -1]).contiguous()
        spatial_attention = torch.softmax(spatial_attention, dim=-1)
        x = x.view([b, c, -1]).contiguous()
        tokens = torch.einsum("bln,bcn->blc", spatial_attention, x)
        return tokens

    def _forward_transformer(self, x: torch.Tensor) -> torch.Tensor:
        if self.with_pos:
            x = x + self.pos_embedding
        x = self.transformer(x)
        return x

    def _forward_transformer_decoder(self, x: torch.Tensor, m: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        if self.with_decoder_pos in ("fix", "learned"):
            x = x + self.pos_embedding_decoder
        x = rearrange(x, "b c h w -> b (h w) c")
        x = self.transformer_decoder(x, m)
        x = rearrange(x, "b (h w) c -> b c h w", h=h)
        return x

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        # 1. Forward through shared ResNet encoder
        x1 = self.forward_single(x1)
        x2 = self.forward_single(x2)

        # 2. Extract semantic tokens
        token1 = self._forward_semantic_tokens(x1)
        token2 = self._forward_semantic_tokens(x2)

        # 3. Model cross-temporal context with Transformer Encoder
        if self.token_trans:
            tokens_ = torch.cat([token1, token2], dim=1)
            tokens = self._forward_transformer(tokens_)
            token1, token2 = tokens.chunk(2, dim=1)

        # 4. Refine with Transformer Decoder
        if self.with_decoder:
            x1 = self._forward_transformer_decoder(x1, token1)
            x2 = self._forward_transformer_decoder(x2, token2)

        # 5. Feature Differencing & Upsampling
        x = torch.abs(x1 - x2)
        if not self.if_upsample_2x:
            x = self.upsamplex2(x)
        x = self.upsamplex4(x)

        # 6. Prediction Head
        logits = self.classifier(x)
        if self.output_sigmoid:
            return self.sigmoid(logits)
        return logits


def load_bit_model(
    checkpoint_path: str = "checkpoints/BIT_LEVIR_best.pt",
    device: str = "cpu"
) -> BitemporalTransformer:
    """Factory function to instantiate BIT and load pretrained 94.7% weights."""
    model = BitemporalTransformer(
        input_nc=3,
        output_nc=2,
        with_pos="learned",
        resnet_stages_num=4,
        token_len=4,
        token_trans=True,
        enc_depth=1,
        dec_depth=8,
        dim_head=64,
        decoder_dim_head=8,
        tokenizer=True,
        if_upsample_2x=True,
        backbone="resnet18",
        decoder_softmax=True,
        with_decoder_pos=None,
        with_decoder=True
    )

    if os.path.exists(checkpoint_path):
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
        state_dict = ckpt["model_G_state_dict"] if "model_G_state_dict" in ckpt else ckpt
        clean_sd = {k.replace("module.", ""): v for k, v in state_dict.items()}
        model.load_state_dict(clean_sd, strict=True)
        print(f"[BIT Model] Successfully loaded weights from {checkpoint_path} onto {device}")
    else:
        print(f"[BIT Model] Warning: Checkpoint {checkpoint_path} not found. Initialized randomly.")

    model.to(device)
    model.eval()
    return model
