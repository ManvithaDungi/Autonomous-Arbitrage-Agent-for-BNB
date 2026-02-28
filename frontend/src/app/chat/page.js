"use client";

import { useState, useEffect } from "react";
import Image from "next/image";

const TokenIcon = ({ token }) => {
  const [imageError, setImageError] = useState(false);
  
  // Deterministic color based on symbol
  const colors = [
    'bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-yellow-600', 
    'bg-red-600', 'bg-indigo-600', 'bg-pink-600', 'bg-orange-600'
  ];
  const colorIndex = token.symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % colors.length;
  const bgColor = colors[colorIndex];

  if (token.logoURI && !imageError) {
    return (
      <img 
        src={token.logoURI} 
        alt={token.symbol} 
        className="w-6 h-6 rounded-full bg-white/10"
        onError={() => setImageError(true)}
      />
    );
  }

  return (
    <div className={`w-6 h-6 rounded-full ${bgColor} flex items-center justify-center text-[10px] font-bold text-white shadow-inner`}>
      {token.symbol[0]}
    </div>
  );
};

export default function Chat() {
  const [tokens, setTokens] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTokens, setSelectedTokens] = useState([]);
  
  // Processing States
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [processingSteps, setProcessingSteps] = useState([
    "Searching for news effecting tokens",
    "Searching for malicious smart contracts",
    "Checking pancake swap profits",
    "Result"
  ]);
  const [stepResults, setStepResults] = useState({});
  const [analysisSummary, setAnalysisSummary] = useState("");
  const [analysisFailed, setAnalysisFailed] = useState(false);
  const [tradePending, setTradePending] = useState(false);
  const [tradeResult, setTradeResult] = useState(null);
  const [recommendedToken, setRecommendedToken] = useState(null);
  const [recommendationError, setRecommendationError] = useState("");
  const [message, setMessage] = useState("");

  // Animation State
  const [isMounted, setIsMounted] = useState(false);

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:53421";

  useEffect(() => {
    setIsMounted(true);
    const fetchTokens = async () => {
      try {
        const response = await fetch('/api/tokens');
        const data = await response.json();
        setTokens(data.tokens);
      } catch (error) {
        console.error('Error fetching tokens:', error);
      }
    };
    fetchTokens();
    const fetchSteps = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/steps`);
        if (!response.ok) return;
        const data = await response.json();
        if (Array.isArray(data.steps) && data.steps.length) {
          setProcessingSteps(data.steps);
        }
      } catch (error) {
        console.error('Error fetching steps:', error);
      }
    };
    const fetchBestToken = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/best-token`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.best) {
          setRecommendedToken(data.best);
          setRecommendationError("");
        }
      } catch (error) {
        setRecommendationError(error.message);
        console.error("Error fetching best token:", error);
      }
    };
    fetchSteps();
    fetchBestToken();
  }, []);

  const buildSummary = (results, tokenSymbol) => {
    const audit = results[1];
    const pancake = results[2];
    const final = results[3]?.result;
    if (!final) {
      return `${tokenSymbol}.`;
    }
    const phase = final.prediction?.phase?.replace(/_/g, " ") || "UNKNOWN";
    const confidence = final.prediction?.confidence ?? "—";
    const action = final.decision?.action || "MONITOR";
    const risk = final.prediction?.risk_level || "MEDIUM";
    const auditSignal = audit?.safe === true
      ? "SAFE TO TRADE"
      : audit?.safe === false
        ? "DO NOT TRADE"
        : "UNVERIFIED";
    const priceDiff = typeof pancake?.price_diff_pct === "number"
      ? `${pancake.price_diff_pct}%`
      : "N/A";

    return `${tokenSymbol} is in ${phase} with ${confidence}/100 confidence (${risk} risk). ` +
      `Action: ${action}. Audit: ${auditSignal}. PancakeSwap price diff: ${priceDiff}.`;
  };

  const handleSend = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    setCurrentStep(0);
    setStepResults({});
    setAnalysisSummary("");
    setAnalysisFailed(false);
    setTradeResult(null);
    setMessage("");

    const tokenSymbol = selectedTokens[0]?.symbol || recommendedToken?.token || "BUSD";
    const endpoints = [
      `${API_BASE}/api/ingestion`,
      `${API_BASE}/api/audit?token=${encodeURIComponent(tokenSymbol)}`,
      `${API_BASE}/api/pancake?token=${encodeURIComponent(tokenSymbol)}&testnet=true`,
      `${API_BASE}/api/result?token=${encodeURIComponent(tokenSymbol)}`
    ];

    try {
      const results = {};
      for (let i = 0; i < endpoints.length; i++) {
        setCurrentStep(i);
        const response = await fetch(endpoints[i]);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data?.error || `Step ${i + 1} failed`);
        }
        results[i] = data;
        setStepResults({ ...results });
      }
      setCurrentStep(endpoints.length);
      setAnalysisSummary(buildSummary(results, tokenSymbol));
    } catch (error) {
      setCurrentStep(processingSteps.length);
      setAnalysisFailed(true);
      setAnalysisSummary(error.message);
    }
  };

  const handleTrade = async (shouldTrade) => {
    if (!shouldTrade) {
      setTradeResult({ status: "SKIPPED", message: "Trade skipped by user." });
      return;
    }
    if (tradePending) return;
    setTradePending(true);
    setTradeResult(null);
    try {
      const tokenSymbol = selectedTokens[0]?.symbol || recommendedToken?.token || "BUSD";
      const response = await fetch(`${API_BASE}/api/trade?token=${encodeURIComponent(tokenSymbol)}`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.result?.reason || data?.error || "Trade failed");
      }
      setTradeResult({ status: "SUCCESS", data: data.result, warning: data.warning });
    } catch (error) {
      setTradeResult({ status: "FAILED", message: error.message });
    } finally {
      setTradePending(false);
    }
  };

  const filteredTokens = tokens.filter(token => 
    token.symbol.toLowerCase().includes(searchQuery.toLowerCase()) || 
    token.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const recommendedTokenObject = recommendedToken
    ? tokens.find(token => token.symbol === recommendedToken.token)
    : null;

  const toggleTokenSelection = (token) => {
    setSelectedTokens(prev => {
      const isSelected = prev.some(t => t.symbol === token.symbol);
      if (isSelected) {
        return prev.filter(t => t.symbol !== token.symbol);
      } else {
        return [...prev, token];
      }
    });
  };

  const removeToken = (symbol) => {
    setSelectedTokens(prev => prev.filter(t => t.symbol !== symbol));
  };

  return (
    <div className="flex h-screen bg-[#0D0D0D] text-white flex-col overflow-hidden relative">
      
      {/* Background Gradients */}
      <div 
        className={`absolute bottom-[-100px] left-1/2 -translate-x-1/2 w-[140%] bg-[radial-gradient(50%_100%_at_50%_100%,#F25C05_0%,transparent_100%)] blur-[60px] pointer-events-none z-0 transition-all duration-[2000ms] ease-out ${
          isMounted ? "h-[50vh] opacity-60" : "h-0 opacity-0"
        }`} 
      />
      <div className="absolute bottom-[-50px] left-1/2 -translate-x-1/2 w-[60%] h-[30vh] bg-[radial-gradient(50%_100%_at_50%_100%,rgba(255,255,255,0.05)_0%,transparent_100%)] opacity-0 hover:opacity-100 transition-opacity duration-500 blur-[40px] pointer-events-auto z-1" />

      {/* Infinite Scrolling Token Marquee OR Search Results */}
      <div className="w-full bg-[#181413]/50 border-b border-[#261d19] h-[60px] flex items-center overflow-hidden relative z-20">
        {isSearching && searchQuery ? (
          <div className="flex items-center gap-4 px-4 overflow-x-auto w-full no-scrollbar">
            {filteredTokens.length > 0 ? (
              filteredTokens.map((token, index) => (
                <div 
                  key={`${token.symbol}-${index}`} 
                  onClick={() => toggleTokenSelection(token)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full border flex-shrink-0 animate-fadeIn cursor-pointer transition-all hover:brightness-110 ${
                    selectedTokens.some(t => t.symbol === token.symbol) 
                      ? 'bg-[#F25C05]/20 border-[#F25C05]' 
                      : 'bg-[#181413] border-[#261d19] hover:bg-[#261d19]'
                  }`}
                >
                  <TokenIcon token={token} />
                  <span className="font-semibold text-sm">{token.symbol}</span>
                  <span className="text-xs text-gray-400">{token.name}</span>
                  {selectedTokens.some(t => t.symbol === token.symbol) && (
                     <div className="ml-2 w-4 h-4 rounded-full bg-[#F25C05] flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" height="12px" viewBox="0 -960 960 960" width="12px" fill="#ffffff"><path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z"/></svg>
                     </div>
                  )}
                </div>
              ))
            ) : (
              <span className="text-gray-500 text-sm px-4">No tokens found</span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-8 animate-scroll whitespace-nowrap min-w-full">
            {[...tokens, ...tokens, ...tokens].map((token, index) => (
              <div key={`${token.symbol}-${index}`} className="flex items-center gap-2 px-4 py-2 bg-[#181413] rounded-full border border-[#261d19]">
                <TokenIcon token={token} />
                <span className="font-semibold text-sm">{token.symbol}</span>
                <span className="text-xs text-gray-400">{token.name}</span>
              </div>
            ))}
          </div>
        )}
        
        {/* Duplicate for seamless loop if needed, though the map above repeats 3 times which is usually enough for standard screens. 
            For CSS animation, we need a continuous flow. 
        */}
        <style jsx>{`
          @keyframes scroll {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
          }
          .animate-scroll {
            animation: scroll 20s linear infinite;
            display: flex;
            width: max-content;
          }
        `}</style>
      </div>

      {/* Search Bar / Pill */}
      <div className="w-full flex justify-center py-4 relative z-20">
        {!isSearching ? (
          <div 
            onClick={() => setIsSearching(true)}
            className="flex items-center gap-2 px-4 py-2 bg-[#181413] rounded-full border border-[#261d19] cursor-pointer hover:bg-[#261d19] transition-all"
          >
            <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="#e3e3e3"><path d="M784-120 532-372q-30 24-69 38t-83 14q-109 0-184.5-75.5T120-580q0-109 75.5-184.5T380-840q109 0 184.5 75.5T640-580q0 44-14 83t-38 69l252 252-56 56ZM380-200q158 0 269-111t111-269q0-158-111-269T380-760q-158 0-269 111t-111 269q0 158 111 269t269 111Z"/></svg>
            <span className="text-sm font-medium text-gray-300">Search tokens</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 animate-fadeIn">
            <div className="flex items-center bg-[#181413] rounded-full border border-[#261d19] px-4 py-2 w-[300px]">
              <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="#e3e3e3" className="mr-2"><path d="M784-120 532-372q-30 24-69 38t-83 14q-109 0-184.5-75.5T120-580q0-109 75.5-184.5T380-840q109 0 184.5 75.5T640-580q0 44-14 83t-38 69l252 252-56 56ZM380-200q158 0 269-111t111-269q0-158-111-269T380-760q-158 0-269 111t-111 269q0 158 111 269t269 111Z"/></svg>
              <input 
                type="text" 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoFocus
                placeholder="Search by name or symbol..."
                className="bg-transparent outline-none text-sm text-white placeholder-gray-500 w-full"
              />
            </div>
            <button 
              onClick={() => { setIsSearching(false); setSearchQuery(""); }}
              className="p-2 bg-[#181413] rounded-full border border-[#261d19] hover:bg-[#261d19] transition-all"
            >
              <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="#e3e3e3"><path d="m256-200-56-56 224-224-224-224 56-56 224 224 224-224 56 56-224 224 224 224-56 56-224-224-224 224Z"/></svg>
            </button>
          </div>
        )}
      </div>


      {recommendedToken && (
        <div className="w-full flex justify-center pb-2 relative z-20">
          <div className="flex items-center gap-3 px-4 py-2 bg-[#181413] rounded-full border border-[#261d19]">
            <span className="text-xs text-gray-300">
              Recommended: <span className="text-[#F25C05] font-semibold">{recommendedToken.token}</span>
              {recommendedToken.action ? ` (${recommendedToken.action})` : ""}
              {typeof recommendedToken.confidence === "number" ? ` · ${recommendedToken.confidence}/100` : ""}
            </span>
            {recommendedTokenObject && (
              <button
                onClick={() => toggleTokenSelection(recommendedTokenObject)}
                className="text-xs px-3 py-1 rounded-full bg-[#F25C05]/20 border border-[#F25C05]/40 text-[#F25C05] hover:brightness-110 transition-all"
              >
                Use
              </button>
            )}
          </div>
        </div>
      )}

      <div className="w-full flex-1 overflow-y-auto p-4 flex flex-col items-center no-scrollbar relative z-10">
        {/* Processing Timeline */}
        {isProcessing && (
          <div className="w-[60vw] mt-8 flex flex-col gap-6 relative animate-fadeIn pl-2">
            {/* Vertical Line - Centered with indicators */}
            <div className="absolute left-[19px] top-[10px] bottom-[10px] w-[1px] bg-gradient-to-b from-[#F25C05] via-[#F25C05]/20 to-transparent opacity-30" />
            
            {processingSteps.map((step, index) => {
              const isActive = index === currentStep;
              const isCompleted = index < currentStep;
              
              return (
                <div key={index} className={`flex items-center gap-4 relative z-10 transition-opacity duration-500 ${isActive || isCompleted ? 'opacity-100' : 'opacity-30'}`}>
                  {/* Indicator */}
                  <div className="relative flex items-center justify-center w-4 h-4">
                    {isActive ? (
                      <div className="relative flex items-center justify-center">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-[#F25C05] opacity-75 animate-ping"></span>
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#F25C05]"></span>
                      </div>
                    ) : isCompleted ? (
                      <div className="w-4 h-4 rounded-full bg-[#F25C05] flex items-center justify-center shadow-[0_0_8px_rgba(242,92,5,0.5)]">
                        <svg xmlns="http://www.w3.org/2000/svg" height="10px" viewBox="0 -960 960 960" width="10px" fill="#ffffff"><path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z"/></svg>
                      </div>
                    ) : (
                      <div className="w-2.5 h-2.5 rounded-full bg-[#261d19] border border-gray-700"></div>
                    )}
                  </div>
                  
                  {/* Text with Shine Effect */}
                  <span className={`text-base font-medium tracking-wide ${
                    isActive ? 'text-transparent bg-clip-text bg-gradient-to-r from-[#F25C05] via-white to-[#F25C05] animate-shine bg-[length:200%_100%]' : 
                    isCompleted ? 'text-[#F25C05]' : 
                    'text-gray-500'
                  }`}>
                    {step}
                  </span>
                </div>
              );
            })}
            
            {currentStep >= processingSteps.length && (
              <div className="mt-4 animate-fadeIn pl-8">
                 <p className="text-gray-300 text-sm leading-relaxed">
                   <span className={`${analysisFailed ? 'text-red-400' : 'text-[#F25C05]'} font-semibold`}>
                     {analysisFailed ? "Analysis Failed:" : "Analysis Complete:"}
                   </span>{" "}
                   {analysisSummary || "Finished."}
                 </p>
                 <div className="mt-4 flex flex-col gap-3">
                   <span className="text-sm text-gray-400">Should you want me to trade?</span>
                   <div className="flex items-center gap-3">
                     <button
                       onClick={() => handleTrade(true)}
                       disabled={tradePending}
                       className={`px-4 py-2 rounded-full text-sm font-semibold border transition-all ${
                         tradePending
                           ? "bg-gray-700 border-gray-600 text-gray-400 cursor-not-allowed"
                           : "bg-[#F25C05] border-[#D94A00] text-white hover:brightness-110"
                       }`}
                     >
                       {tradePending ? "Trading..." : "Should Trade"}
                     </button>
                     <button
                       onClick={() => handleTrade(false)}
                       disabled={tradePending}
                       className="px-4 py-2 rounded-full text-sm font-semibold border border-gray-600 text-gray-300 hover:bg-gray-800 transition-all"
                     >
                       Don't Trade
                     </button>
                   </div>
                   {tradeResult && (
                     <div className="text-xs text-gray-400">
                      {tradeResult.status === "SUCCESS" && (
                        <span className="text-green-400">
                          Trade executed. TX: {tradeResult.data?.tx_hash || "N/A"}{" "}
                          {tradeResult.warning ? `(${tradeResult.warning})` : ""}
                        </span>
                      )}
                       {tradeResult.status === "FAILED" && (
                         <span className="text-red-400">
                           Trade failed: {tradeResult.message}
                         </span>
                       )}
                       {tradeResult.status === "SKIPPED" && (
                         <span className="text-gray-400">{tradeResult.message}</span>
                       )}
                     </div>
                   )}
                 </div>
              </div>
            )}
            
            <style jsx>{`
              @keyframes shine {
                0% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
              }
              .animate-shine {
                animation: shine 3s linear infinite;
              }
              /* Hide scrollbar for Chrome, Safari and Opera */
              .no-scrollbar::-webkit-scrollbar {
                  display: none;
              }
              /* Hide scrollbar for IE, Edge and Firefox */
              .no-scrollbar {
                  -ms-overflow-style: none;  /* IE and Edge */
                  scrollbar-width: none;  /* Firefox */
              }
            `}</style>
          </div>
        )}
      </div>
      <div className="w-full flex-none flex items-center justify-center pb-10 pt-4 relative z-20">
        <div className="w-[60vw] bg-[#181413] rounded-[24px] border border-[#261d19] flex flex-col p-4 shadow-2xl relative z-10">
            <textarea 
              className="w-full h-[80px] bg-transparent outline-none px-2 text-[18px] text-white placeholder-gray-500 font-medium resize-none"
              placeholder="Type a message..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <div className="flex justify-between items-end mt-2">
              <div className="flex flex-wrap gap-2 max-w-[70%]">
                {selectedTokens.map(token => (
                  <div key={token.symbol} className="flex items-center gap-1.5 pl-2 pr-1 py-1 bg-[#261d19] rounded-full border border-[#F25C05]/30 group hover:border-[#F25C05] transition-colors">
                    <TokenIcon token={token} />
                    <span className="text-xs font-medium text-gray-200">{token.symbol}</span>
                    <button 
                      onClick={() => removeToken(token.symbol)}
                      className="w-4 h-4 rounded-full bg-white/10 flex items-center justify-center hover:bg-[#F25C05] text-gray-400 hover:text-white transition-all ml-1"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" height="10px" viewBox="0 -960 960 960" width="10px" fill="currentColor"><path d="m256-200-56-56 224-224-224-224 56-56 224 224 224-224 56 56-224 224 224 224-56 56-224-224-224 224Z"/></svg>
                    </button>
                  </div>
                ))}
              </div>
              <button 
                onClick={handleSend}
                disabled={isProcessing}
                className={`h-[40px] px-6 rounded-[10px] flex items-center justify-center shadow-[inset_0px_1px_0px_0px_rgba(255,255,255,0.2),0px_4px_10px_rgba(0,0,0,0.3)] transition-all border ${
                  isProcessing
                    ? "bg-gray-700 border-gray-600 text-gray-300 cursor-not-allowed"
                    : "bg-gradient-to-b from-[#F25C05] to-[#D94A00] border-[#D94A00] hover:brightness-110"
                }`}
              >
                <span className="font-semibold text-white text-[14px] tracking-wide">
                  {isProcessing ? "Processing..." : "Send"}
                </span>
              </button>
            </div>
        </div>
      </div>
    </div>
  );
}