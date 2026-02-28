import hre from "hardhat";

async function main() {
  console.log("Initiating ArbitrageExecutor deployment to BNB Testnet...");

  const { ethers } = await hre.network.connect();
  const ArbitrageExecutor = await ethers.getContractFactory("ArbitrageExecutor");

  const arbitrageExecutor = await ArbitrageExecutor.deploy();
  await arbitrageExecutor.waitForDeployment();

  const contractAddress = await arbitrageExecutor.getAddress();
  
  console.log(`Success! ArbitrageExecutor deployed to: ${contractAddress}`);
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});