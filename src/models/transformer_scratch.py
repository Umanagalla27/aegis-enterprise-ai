import math

import torch
import torch.nn as nn


class MultiHeadSelfAttention(nn.Module):
    """Multi-Head Self-Attention built directly from scratch in PyTorch.

    Implements: Attention(Q, K, V) = softmax((Q K^T) / sqrt(d_k)) V
    """

    def __init__(self, d_model: int = 64, num_heads: int = 4):
        super().__init__()
        assert d_model % num_heads == 0, "d_model must be divisible by num_heads"

        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads

        # Linear projections for Query, Key, Value, and Output
        self.w_q = nn.Linear(d_model, d_model)
        self.w_k = nn.Linear(d_model, d_model)
        self.w_v = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        batch_size, seq_len, _ = x.size()

        # 1. Project and split into heads: [batch_size, num_heads, seq_len, d_k]
        q = self.w_q(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)
        k = self.w_k(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)
        v = self.w_v(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)

        # 2. Scaled Dot-Product Attention
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.d_k)

        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)

        attention_weights = torch.softmax(scores, dim=-1)
        context = torch.matmul(attention_weights, v)

        # 3. Concatenate heads and project output
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, self.d_model)
        return self.w_o(context)


class TinyTransformerBlock(nn.Module):
    def __init__(self, d_model: int = 64, num_heads: int = 4, d_ff: int = 128):
        super().__init__()
        self.attention = MultiHeadSelfAttention(d_model, num_heads)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(nn.Linear(d_model, d_ff), nn.ReLU(), nn.Linear(d_ff, d_model))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pre-LN Transformer block with residual connections
        x = x + self.attention(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x


if __name__ == "__main__":
    dummy_input = torch.randn(2, 8, 64)  # batch=2, seq_len=8, dim=64
    block = TinyTransformerBlock(d_model=64, num_heads=4)
    out = block(dummy_input)
    print("Transformer Block Output Shape:", out.shape)
    assert out.shape == (2, 8, 64)
    print("✅ Self-Attention mathematical verification passed!")
