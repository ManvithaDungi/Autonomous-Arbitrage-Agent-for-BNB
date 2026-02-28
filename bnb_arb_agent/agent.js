import { spawn } from 'child_process';
import { ethers } from "ethers";
import dotenv from "dotenv";

// Load your private key from the .env file
dotenv.config();
const PRIVATE_KEY = process.env.PRIVATE_KEY ?? "";

// 1. Direct connection to the Binance Testnet
const RPC_URL = "https://data-seed-prebsc-1-s1.binance.org:8545/";

const ARBITRAGE_CONTRACT = "0xB93d709B121E4cE93DED04474241a548D2597ad5";
const PANCAKE_ROUTER = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1";
const WBNB = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd";

// 2. We define the minimal ABI so Ethers knows what function to call
const ABI = [
    "function executeArbitrage(address routerA, address routerB, address tokenA, address tokenB, uint256 amountIn) external"
];

async function runTrade(tokenAddress, amount) {
    console.log("🤖 Agent: Triggering On-Chain Arbitrage directly via Ethers.js...");

    // 3. Set up the Provider and Wallet (Bypassing Hardhat)
    const provider = new ethers.JsonRpcProvider(RPC_URL);
    const wallet = new ethers.Wallet(PRIVATE_KEY, provider);
    
    // Connect to your deployed contract
    const contract = new ethers.Contract(ARBITRAGE_CONTRACT, ABI, wallet);

    try {
        const tx = await contract.executeArbitrage(
            PANCAKE_ROUTER, 
            PANCAKE_ROUTER, 
            WBNB, 
            tokenAddress, 
            ethers.parseEther(amount),
            { 
                gasLimit: 3000000 
            } 
        );
        
        console.log(`✅ Trade Sent to Mempool! Hash: ${tx.hash}`);
        console.log(`⏳ Waiting for BSC Testnet miners to confirm the block...`);
        
        // Wait for the block to be mined
        const receipt = await tx.wait();
        
        console.log(`🏆 SUCCESS! Transaction Mined in Block: ${receipt.blockNumber}`);
        
    } catch (err) {
        console.log(`❌ Transaction Failed or Reverted!`);
        console.log(`Reason: ${err.shortMessage || err.message}`);
    }
}

// --- PYTHON MONITOR BRIDGE ---
const monitor = spawn('python', ['-u', 'monitor.py']);

monitor.stdout.on('data', async (data) => {
    const output = data.toString();
    process.stdout.write(output);

    if (output.includes('SIGNAL:')) {
        try {
            const jsonPart = output.split('SIGNAL:')[1].trim();
            const signal = JSON.parse(jsonPart);

            if (signal.is_simulation) {
                console.log(`\n🧪 [SIMULATION] Trade detected for ${signal.token_name}. Parameters verified.\n`);
            } else {
                console.log(`\n💰 [REAL TRADE] Triggering On-Chain...`);
                await runTrade(signal.token, signal.amount);
            }
        } catch (e) {
            console.log("JSON Parse Error: Check Python output format.");
        }
    }
});

monitor.stderr.on('data', (data) => {
    console.error(`\n⚠️ [Python Error]: ${data}`);
});

monitor.on('close', (code) => {
    console.log(`\n⛔ Monitor process exited with code ${code}. Check for errors above.`);
});