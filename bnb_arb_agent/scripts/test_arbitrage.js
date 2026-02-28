import hre from "hardhat";

async function main() {
  // 1. YOUR DEPLOYED CONTRACT
  const ARBITRAGE_ADDRESS = "0xB93d709B121E4cE93DED04474241a548D2597ad5"; 

  // 2. OFFICIAL BSC TESTNET ADDRESSES
  const WBNB = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"; // Wrapped BNB
  const BUSD = "0xed24fc36d5ee211ea25a80239fb8c4cfd80f12ee"; // Testnet BUSD
  const PANCAKE_ROUTER = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1";

  const { ethers } = await hre.network.connect();
  const [signer] = await ethers.getSigners();

  console.log("Step A: Funding the contract with WBNB...");
  
  // Minimal human-readable ABI to interact with WBNB
  const wbnbAbi = [
    "function deposit() public payable",
    "function transfer(address to, uint256 value) public returns (bool)",
    "function balanceOf(address account) public view returns (uint256)"
  ];
  const wbnbContract = new ethers.Contract(WBNB, wbnbAbi, signer);

  // Convert 0.05 tBNB into WBNB (Standard for DeFi trades)
  const amountToFund = ethers.parseEther("0.05"); 
  let tx = await wbnbContract.deposit({ value: amountToFund });
  await tx.wait();
  
  // Transfer that 0.05 WBNB to your deployed arbitrage contract
  tx = await wbnbContract.transfer(ARBITRAGE_ADDRESS, amountToFund);
  await tx.wait();

  const balance = await wbnbContract.balanceOf(ARBITRAGE_ADDRESS);
  console.log(`Contract funded! Arbitrage bot currently holds: ${ethers.formatEther(balance)} WBNB\n`);

  console.log("Step B: Executing Arbitrage Test (Expecting a Revert)...");
  
  const arbitrageExecutor = await ethers.getContractAt("ArbitrageExecutor", ARBITRAGE_ADDRESS);

  try {
    // We pass the PancakeSwap router TWICE. 
    // This forces a fee-loss, which should trigger your safety revert.
    const executeTx = await arbitrageExecutor.executeArbitrage(
      PANCAKE_ROUTER, // DEX A
      PANCAKE_ROUTER, // DEX B (Same DEX = guaranteed fee loss)
      WBNB,           // Token A
      BUSD,           // Token B
      amountToFund    // Use the 0.05 WBNB we just funded
    );
    await executeTx.wait();
    console.log("Wait, the transaction succeeded? This shouldn't happen!");

  } catch (error) {
    // Check if the error matches our custom Solidity require() statement
    if (error.message.includes("Trade not profitable! Reverting...")) {
      console.log("✅ SUCCESS! The contract caught the unprofitable trade and safely reverted it.");
      console.log("Your capital is protected!");
    } else {
      console.error("An unexpected error occurred:", error.message);
    }
  }
}

main().catch((error) => {
  console.error("Script failed:", error);
  process.exitCode = 1;
});