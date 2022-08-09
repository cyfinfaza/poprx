const client = new WebSocket("ws://localhost:6002");
client.onmessage = function (event) {
  const data = JSON.parse(event.data);
  console.log("poprx:", data);
};
client.onopen = function (event) {
  client.send(
    JSON.stringify({
      type: "txinit",
      data: { id: Math.floor(Math.random() * 900000) + 100000, agent: navigator.userAgent, path: window.location.pathname },
    })
  );
};
