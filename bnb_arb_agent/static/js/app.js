(function () {
  const form = document.getElementById("run-form");
  const loading = document.getElementById("loading");
  if (!form || !loading) return;

  form.addEventListener("submit", function () {
    loading.classList.add("active");
    loading.setAttribute("aria-hidden", "false");
  });
})();
