/** Entry point: `npm start` (configuration via environment variables, docs/03 §3.1). */
import { buildApp } from "./app.js";
import { settingsFromEnv, type Settings } from "./config.js";

let settings: Settings;
try {
  settings = settingsFromEnv(process.env);
} catch (err) {
  console.error(`configuration error: ${(err as Error).message}`);
  process.exit(2);
}

const app = buildApp(settings, { logger: true });
app.listen({ host: settings.host, port: settings.port }).catch((err: Error) => {
  app.log.error(err.message);
  process.exit(1);
});
