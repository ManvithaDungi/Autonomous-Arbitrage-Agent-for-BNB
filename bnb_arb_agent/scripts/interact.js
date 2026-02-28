import hre from "hardhat";

async function main() {
  // Replace this with your actual deployed contract address
  const CONTRACT_ADDRESS = "0xC50822Fd22f3A791257b29600F658fE2d08983A8"; 

  console.log(`Connecting to contract at: ${CONTRACT_ADDRESS}`);

  // Connect to the network just like in the deploy script
  const { ethers } = await hre.network.connect();

  // Attach to the deployed contract using its name and address
  const connectionTest = await ethers.getContractAt("ConnectionTest", CONTRACT_ADDRESS);

  // 1. READ: Fetch the current state from the blockchain
  console.log("Fetching current status...");
  let currentStatus = await connectionTest.status();
  console.log(`Status on-chain: "${currentStatus}"\n`);

  // 2. WRITE: Send a transaction to change the state
  console.log("Sending transaction to update status...");
  const tx = await connectionTest.updateStatus("System Check: All systems go for Arbitrage Bot!");
  
  // Wait for the block to be mined
  await tx.wait();
  console.log("Transaction confirmed in block!\n");

  // 3. READ AGAIN: Verify the update worked
  console.log("Fetching updated status...");
  currentStatus = await connectionTest.status();
  console.log(`New Status on-chain: "${currentStatus}"`);
}

main().catch((error) => {
  console.error("Interaction failed:", error);
  process.exitCode = 1;
});