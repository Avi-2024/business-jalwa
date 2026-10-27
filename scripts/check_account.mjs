const token = (process.env.META_ACCESS_TOKEN || "").trim();
const id = process.env.IG_USER_ID || "";
if (!token || !/^\d+$/.test(id)) throw new Error("Configure META_ACCESS_TOKEN secret and numeric IG_USER_ID variable.");
const response = await fetch("https://graph.instagram.com/v23.0/" + id + "?fields=id,username", {headers:{Authorization:"Bearer " + token}});
const data = await response.json();
if (!response.ok || data.error) throw new Error("Instagram account check failed. Check token, permissions and account ID.");
if (data.username !== "business.jalwa") throw new Error("Wrong Instagram account; expected business.jalwa.");
console.log("Verified @business.jalwa; account ID: " + data.id);
