import hre from "hardhat";

async function main() {
  console.log("Initiating deployment to BNB Testnet...");

  // 1. Connect to the network to get the scoped ethers instance (Hardhat v3 requirement)
  const { ethers } = await hre.network.connect();

  // 2. Access the ContractFactory through the scoped ethers object
  const ConnectionTest = await ethers.getContractFactory("ConnectionTest");

  // Deploy the contract to the network
  const connectionTest = await ConnectionTest.deploy();

  // Wait for the transaction to be confirmed on the blockchain
  await connectionTest.waitForDeployment();

  // Retrieve the official contract address
  const contractAddress = await connectionTest.getAddress();
  
  console.log(`Success! ConnectionTest deployed to: ${contractAddress}`);
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});