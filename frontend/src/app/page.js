"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

export default function Home() {
  const [walletAddress, setWalletAddress] = useState("");
  const [isMounted, setIsMounted] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const connectWallet = async () => {
    if (typeof window.ethereum !== "undefined") {
      try {
        const accounts = await window.ethereum.request({
          method: "eth_requestAccounts",
        });
        setWalletAddress(accounts[0]);
        console.log("Connected", accounts[0]);
        // Redirect to chat page after successful connection
        router.push("/chat");
      } catch (error) {
        console.error("Error connecting wallet", error);
      }
    } else {
      alert("Please install MetaMask!");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0D0D0D] relative overflow-hidden flex-col">
        
        <div 
          className={`absolute bottom-[-100px] left-1/2 -translate-x-1/2 w-[140%] bg-[radial-gradient(50%_100%_at_50%_100%,#F25C05_0%,transparent_100%)] blur-[60px] pointer-events-none z-0 transition-all duration-[2000ms] ease-out ${
            isMounted ? "h-[50vh] opacity-60" : "h-0 opacity-0"
          }`} 
        />
        
        <div className="absolute bottom-[-50px] left-1/2 -translate-x-1/2 w-[60%] h-[30vh] bg-[radial-gradient(50%_100%_at_50%_100%,rgba(255,255,255,0.05)_0%,transparent_100%)] opacity-0 hover:opacity-100 transition-opacity duration-500 blur-[40px] pointer-events-auto z-1" />

        <span className="geist-semi text-[60px] mb-2">Let's get started</span>
        <div 
          onClick={connectWallet}
          className="w-[320px] h-[50px] rounded-[12px] bg-gradient-to-b from-[#F25C05] to-[#D94A00] flex items-center justify-center cursor-pointer shadow-[inset_0px_1px_0px_0px_rgba(255,255,255,0.2),0px_4px_10px_rgba(0,0,0,0.3)] hover:brightness-110 transition-all border border-[#D94A00] z-10 relative">
          <div className="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="#e3e3e3"><path d="M280-160v-40h-40q-50 0-85-35t-35-85v-120H40v-80h80v-120q0-50 35-85t85-35h40v-40h80v640h-80Zm-40-120h40v-400h-40q-17 0-28.5 11.5T200-640v320q0 17 11.5 28.5T240-280Zm360 120v-160H440v-80h160v-160H440v-80h160v-160h80v40h40q50 0 85 35t35 85v120h80v80h-80v120q0 50-35 85t-85 35h-40v40h-80Zm80-120h40q17 0 28.5-11.5T760-320v-320q0-17-11.5-28.5T720-680h-40v400ZM280-480Zm400 0Z"/></svg>
            <span className="font-semibold text-white text-[16px] tracking-wide">
              {walletAddress ? 
                `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}` : 
                "Connect your wallet"
              }
            </span>
          </div>
        </div>
    </div>
  );
}
