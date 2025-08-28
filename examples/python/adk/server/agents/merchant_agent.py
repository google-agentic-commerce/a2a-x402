"""Merchant agent with exception-based x402 payment requirements."""

import json
import os
from pathlib import Path
from typing import List, Dict, Any

from a2a.types import Message, Part, TextPart
from google.adk.agents import LlmAgent

# Import from the refactored a2a_x402 package
from a2a_x402 import (
    require_payment,
    X402PaymentRequiredException,
    get_extension_declaration,
    create_merchant_agent_card as _create_merchant_agent_card
)


class MerchantAgent:
    """Business logic agent that throws payment exceptions for paid services."""
    
    def __init__(self):
        self.merchant_address = os.getenv('MERCHANT_ADDRESS')
        if not self.merchant_address:
            raise ValueError("MERCHANT_ADDRESS environment variable is required")
        
        # Load service catalog
        products_path = Path(__file__).parent.parent / "products.json"
        with open(products_path) as f:
            self.catalog = json.load(f)
    
    async def execute(self, message_batch: List[Message]) -> List[Message]:
        """Process messages with dynamic payment requirements."""
        responses = []
        
        for message in message_batch:
            try:
                response = await self._process_message(message)
                responses.append(response)
            except X402PaymentRequiredException:
                # Let the X402ServerExecutor handle payment exceptions
                raise
            except Exception as e:
                # Handle other errors gracefully
                error_response = Message(
                    messageId=f"error-{message.messageId}",
                    role="agent",
                    parts=[TextPart(
                        kind="text",
                        text=f"Sorry, I encountered an error: {str(e)}"
                    )]
                )
                responses.append(error_response)
        
        return responses
    
    async def _process_message(self, message: Message) -> Message:
        """Process individual message and determine if payment is required."""
        # Extract text from message
        text_parts = [part for part in message.parts if isinstance(part, TextPart)]
        if not text_parts:
            return self._create_error_response(message, "No text content found in message")
        
        user_message = " ".join(part.text for part in text_parts).lower()
        
        # Route to appropriate service handler
        if any(keyword in user_message for keyword in ['catalog', 'list', 'services', 'available']):
            return await self._handle_catalog_request(message)
        elif any(keyword in user_message for keyword in ['status', 'health', 'ping']):
            return await self._handle_status_request(message)  
        elif any(keyword in user_message for keyword in ['summary', 'overview', 'brief']):
            return await self._handle_summary_request(message)
        elif any(keyword in user_message for keyword in ['basic', 'simple', 'quick'] + ['analysis']):
            return await self._handle_basic_analysis_request(message, user_message)
        elif any(keyword in user_message for keyword in ['premium', 'advanced', 'ai'] + ['analysis']):
            return await self._handle_premium_analysis_request(message, user_message)
        elif any(keyword in user_message for keyword in ['report', 'custom', 'tailored']):
            return await self._handle_custom_report_request(message, user_message)
        elif any(keyword in user_message for keyword in ['alert', 'notification', 'setup']):
            return await self._handle_alerts_setup_request(message, user_message)
        else:
            return await self._handle_general_inquiry(message, user_message)
    
    async def _handle_catalog_request(self, message: Message) -> Message:
        """Handle free service catalog requests."""
        services_text = "🏪 **Available Services**\\n\\n"
        
        # Free services
        services_text += "**Free Services:**\\n"
        for service in self.catalog["free_services"]:
            services_text += f"• {service['name']}: {service['description']}\\n"
        
        services_text += "\\n**Paid Services:**\\n"
        for service in self.catalog["services"]:
            services_text += f"• {service['name']} ({service['price']}): {service['description']} | Duration: {service['duration']}\\n"
        
        services_text += "\\n💡 Just ask for any service by name to get started!"
        
        return Message(
            messageId=f"catalog-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=services_text)]
        )
    
    async def _handle_status_request(self, message: Message) -> Message:
        """Handle free system status requests."""
        status_text = """🟢 **System Status: All Systems Operational**
        
**Services Available:**
• Payment processing: ✅ Active
• Data analysis: ✅ Active  
• Report generation: ✅ Active
• Real-time alerts: ✅ Active

**Network:** Base (Coinbase L2)
**Payment Asset:** USDC
**Merchant Address:** {}

Ready to serve your data analysis needs!""".format(self.merchant_address[:10] + "..." + self.merchant_address[-8:])
        
        return Message(
            messageId=f"status-{message.messageId}",
            role="agent", 
            parts=[TextPart(kind="text", text=status_text)]
        )
    
    async def _handle_summary_request(self, message: Message) -> Message:
        """Handle free market summary requests."""
        summary_text = """📊 **Quick Market Summary** (Free Preview)
        
**Today's Highlights:**
• Market sentiment: Cautiously optimistic
• Major indices: Mixed performance
• Crypto markets: Stabilizing after recent volatility
• Tech sector: Leading gains

*For detailed analysis with predictions and actionable insights, try our Premium AI Analysis ($5.00)*

**Available Paid Services:**
• Basic Analysis ($1.50) - Key metrics and trends
• Premium AI Analysis ($5.00) - Comprehensive insights with predictions  
• Custom Reports ($3.00) - Tailored to your needs"""
        
        return Message(
            messageId=f"summary-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=summary_text)]
        )
    
    async def _handle_basic_analysis_request(self, message: Message, user_message: str) -> Message:
        """Handle paid basic analysis requests - throws payment exception."""
        # This is a paid service - throw payment exception
        raise require_payment(
            price="$1.50",
            pay_to_address=self.merchant_address,
            resource="/basic-analysis",
            description="Basic market analysis with key metrics and trends"
        )
        
        # This code runs after payment is verified and settled
        return await self._provide_basic_analysis(message, user_message)
    
    async def _handle_premium_analysis_request(self, message: Message, user_message: str) -> Message:
        """Handle paid premium analysis requests - throws payment exception."""
        # This is a paid service - throw payment exception  
        raise require_payment(
            price="$5.00",
            pay_to_address=self.merchant_address,
            resource="/premium-analysis",
            description="Comprehensive AI-powered market analysis with predictions and insights"
        )
        
        # This code runs after payment is verified and settled
        return await self._provide_premium_analysis(message, user_message)
    
    async def _handle_custom_report_request(self, message: Message, user_message: str) -> Message:
        """Handle paid custom report requests - throws payment exception."""
        # This is a paid service - throw payment exception
        raise require_payment(
            price="$3.00", 
            pay_to_address=self.merchant_address,
            resource="/custom-report",
            description="Tailored data report based on your specific requirements"
        )
        
        # This code runs after payment is verified and settled
        return await self._provide_custom_report(message, user_message)
    
    async def _handle_alerts_setup_request(self, message: Message, user_message: str) -> Message:
        """Handle paid alerts setup requests - throws payment exception."""
        # This is a paid service - throw payment exception
        raise require_payment(
            price="$2.50",
            pay_to_address=self.merchant_address, 
            resource="/alerts-setup",
            description="Configure personalized real-time market alerts"
        )
        
        # This code runs after payment is verified and settled
        return await self._provide_alerts_setup(message, user_message)
    
    async def _provide_basic_analysis(self, message: Message, user_message: str) -> Message:
        """Provide basic analysis after payment confirmation."""
        analysis_text = """📈 **Basic Market Analysis** - PAID SERVICE DELIVERED
        
**Key Metrics (Last 24h):**
• S&P 500: +0.8% (4,847 pts)
• NASDAQ: +1.2% (15,234 pts)  
• DOW: +0.5% (38,967 pts)
• VIX: 14.2 (-2.1%)

**Sector Performance:**
• Technology: +1.8% 📱
• Healthcare: +0.9% 🏥
• Financial: +0.6% 🏦
• Energy: -0.3% ⚡

**Trading Volume:** Above average (+15%)
**Market Breadth:** 68% of stocks advancing

**Key Takeaway:** Market showing resilience with tech leadership. Volume suggests institutional participation.

✅ **Analysis Complete** - Thank you for your payment!"""
        
        return Message(
            messageId=f"basic-analysis-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=analysis_text)]
        )
    
    async def _provide_premium_analysis(self, message: Message, user_message: str) -> Message:
        """Provide premium analysis after payment confirmation."""
        analysis_text = """🤖 **Premium AI Analysis** - PAID SERVICE DELIVERED
        
**Comprehensive Market Intelligence:**

**Technical Analysis:**
• RSI: 58.2 (neutral zone, room for upside)
• MACD: Bullish crossover confirmed
• 50-day MA: Strong support at 4,820
• Volume Profile: Institutional accumulation detected

**AI Sentiment Analysis:**
• Social media sentiment: 72% positive
• News sentiment: 68% optimistic  
• Options flow: Moderate bullish bias
• Insider activity: Net buying (+$2.3M)

**Predictive Modeling Results:**
• 5-day forecast: 65% probability of +2-4% move
• Key resistance: 4,920 (strong), 4,980 (major)
• Support levels: 4,820 (immediate), 4,760 (strong)

**Sector Rotation Signals:**
• Technology: Outperform (High confidence)
• Healthcare: Neutral-Positive  
• Energy: Underperform near-term

**Risk Assessment:**
• Market Risk: Medium (geopolitical factors)
• Liquidity Risk: Low (strong volume)
• Volatility Risk: Low-Medium

**Action Items:**
1. Consider tech exposure on pullbacks to 4,820
2. Watch for breakout above 4,920 for momentum plays
3. Hedge with VIX positions if approaching 4,980

✅ **Premium Analysis Complete** - Powered by our proprietary AI models!"""
        
        return Message(
            messageId=f"premium-analysis-{message.messageId}",
            role="agent", 
            parts=[TextPart(kind="text", text=analysis_text)]
        )
    
    async def _provide_custom_report(self, message: Message, user_message: str) -> Message:
        """Provide custom report after payment confirmation.""" 
        report_text = """📋 **Custom Data Report** - PAID SERVICE DELIVERED
        
**Report Generated Based on Your Request:** "{}"

**Executive Summary:**
Tailored analysis focusing on the specific metrics and timeframes you requested.

**Key Data Points:**
• Custom KPI #1: 94.2% (vs. benchmark 89.1%)
• Custom KPI #2: $4.7M (quarterly growth +12%)
• Custom KPI #3: 2.8x efficiency ratio
• Risk-adjusted return: 18.4%

**Methodology:**
• Data sources: 15+ verified feeds
• Time period: Customized to your requirements  
• Statistical significance: 95% confidence interval
• Peer comparison: Top 25 comparable entities

**Strategic Recommendations:**
1. **Immediate (0-30 days):** Optimize allocation based on momentum signals
2. **Short-term (1-3 months):** Monitor custom threshold triggers
3. **Long-term (3-12 months):** Strategic positioning for identified opportunities

**Custom Metrics Dashboard:**
• Performance vs. custom benchmark: +5.7%
• Volatility-adjusted score: 8.4/10
• Correlation to your specified factors: 0.73

**Next Steps:**
Regular monitoring suggested with weekly updates available.

✅ **Custom Report Complete** - Tailored specifically for your requirements!""".format(user_message[:50] + "..." if len(user_message) > 50 else user_message)
        
        return Message(
            messageId=f"custom-report-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=report_text)]
        )
    
    async def _provide_alerts_setup(self, message: Message, user_message: str) -> Message:
        """Provide alerts setup after payment confirmation."""
        alerts_text = """🔔 **Real-time Alerts Setup** - PAID SERVICE DELIVERED
        
**Alert System Configured Successfully!**

**Active Alert Rules:**
1. **Price Alerts:** 
   - S&P 500 > 4,920 (breakout signal)
   - S&P 500 < 4,820 (support test)
   
2. **Volume Alerts:**
   - Daily volume > 120% of 20-day average
   - Unusual options activity detected
   
3. **Sentiment Alerts:**
   - AI sentiment score drops below 40%
   - Major news sentiment shift > 15%
   
4. **Technical Alerts:**
   - RSI oversold < 30 (buy opportunity)
   - RSI overbought > 70 (profit taking)
   
**Delivery Methods Configured:**
• Priority alerts: Immediate push notification
• Standard alerts: Email digest (every 2 hours)
• Weekly summary: Comprehensive report

**Custom Thresholds Set:**
Based on your message, we've configured personalized thresholds matching your risk tolerance and trading style.

**Alert Backtesting Results:**
• Historical accuracy: 78.4%
• False positive rate: 12.1%  
• Average lead time: 47 minutes

**Management:**
• View/edit alerts: Use command "manage alerts"
• Pause alerts: "pause alerts [duration]"
• Alert history: "alert performance"

✅ **Alert System Active** - You'll receive notifications based on your configured preferences!"""
        
        return Message(
            messageId=f"alerts-setup-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=alerts_text)]
        )
    
    async def _handle_general_inquiry(self, message: Message, user_message: str) -> Message:
        """Handle general inquiries and guide users to available services."""
        response_text = """👋 **Welcome to our AI-Powered Market Intelligence Service!**
        
I can help you with various data analysis and market intelligence services. Here's what I offer:

**Free Services:**
• 📋 Service catalog ("list services")
• 🟢 System status ("system status")  
• 📊 Quick market summary ("market summary")

**Paid Services:**
• 📈 Basic Market Analysis ($1.50) - Key metrics and trends
• 🤖 Premium AI Analysis ($5.00) - Comprehensive insights with AI predictions
• 📋 Custom Data Reports ($3.00) - Tailored analysis for your needs
• 🔔 Real-time Alerts Setup ($2.50) - Personalized market notifications

**How it works:**
1. Simply ask for any service by name
2. For paid services, I'll request payment through our secure x402 protocol
3. Once payment is confirmed, I'll deliver your analysis immediately

**Examples:**
• "I want a premium analysis"
• "Set up alerts for me"  
• "Create a custom report on tech stocks"

What can I help you analyze today?"""
        
        return Message(
            messageId=f"inquiry-{message.messageId}",
            role="agent",
            parts=[TextPart(kind="text", text=response_text)]
        )
    
    def _create_error_response(self, message: Message, error_msg: str) -> Message:
        """Create an error response message."""
        return Message(
            messageId=f"error-{message.messageId}",
            role="agent", 
            parts=[TextPart(kind="text", text=f"❌ Error: {error_msg}")]
        )


def create_merchant_agent_card():
    """Create the agent card for the merchant agent."""
    # Get merchant address from environment
    merchant_address = os.getenv('MERCHANT_ADDRESS', '0x1234567890123456789012345678901234567890')
    
    return _create_merchant_agent_card(
        merchant_address=merchant_address,
        url="http://localhost:10000/agents/market-intelligence"
    )