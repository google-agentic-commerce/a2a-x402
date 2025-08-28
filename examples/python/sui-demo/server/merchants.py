#!/usr/bin/env python3
"""
Merchant configurations - add new merchants here.
"""

from merchant_base import MerchantConfig

# All available merchants - add new ones here and they'll be automatically available
MERCHANTS = {
    "penny_snacks": MerchantConfig(
        name="Penny Snacks",
        description="A corner store selling affordable snacks and treats",
        products=[
            {"name": "Chocolate Bar", "price": 0.03},
            {"name": "Gummy Bears", "price": 0.02},
            {"name": "Potato Chips", "price": 0.04},
            {"name": "Soda Can", "price": 0.05},
            {"name": "Cookie Pack", "price": 0.03},
            {"name": "Mint Candy", "price": 0.01},
            {"name": "Fruit Snacks", "price": 0.02}
        ]
    ),
    
    "tiny_tools": MerchantConfig(
        name="Tiny Tools", 
        description="A miniature hardware store with small tools and supplies",
        products=[
            {"name": "Mini Screwdriver", "price": 0.02},
            {"name": "Small Wrench", "price": 0.03},
            {"name": "Tiny Hammer", "price": 0.04},
            {"name": "Pocket Ruler", "price": 0.01},
            {"name": "Mini Pliers", "price": 0.03},
            {"name": "Small Nails", "price": 0.01}
        ]
    ),
    
    "digital_bits": MerchantConfig(
        name="Digital Bits",
        description="A micro electronics store with tiny digital components", 
        products=[
            {"name": "LED Light", "price": 0.01},
            {"name": "Small Battery", "price": 0.02},
            {"name": "Micro Cable", "price": 0.03},
            {"name": "Tiny Speaker", "price": 0.04},
            {"name": "Mini Button", "price": 0.01},
            {"name": "Small Switch", "price": 0.02}
        ]
    ),
}