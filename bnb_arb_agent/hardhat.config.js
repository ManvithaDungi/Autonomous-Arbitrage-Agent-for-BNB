import { defineConfig } from "hardhat/config";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";
import hardhatVerify from "@nomicfoundation/hardhat-verify";
import dotenv from "dotenv";

dotenv.config();

const PRIVATE_KEY = process.env.PRIVATE_KEY ?? "";

export default defineConfig({
  defaultNetwork: "bscTestnet", 
  plugins: [hardhatEthers, hardhatVerify], 
  solidity: {
    version: "0.8.24",
  },
  paths: {
    sources: "./contracts",
  },
  networks: {
    bscTestnet: {
      type: "http",     
      chainType: "l1",  
      url: "https://data-seed-prebsc-1-s1.binance.org:8545/",
      chainId: 97,
      accounts: PRIVATE_KEY ? [PRIVATE_KEY] : [],
    }
  }
});