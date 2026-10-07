import engine.gameManager.ConfigManager;

public final class CredentialLoggingSmoke {
    public static void main(String[] args) {
        for (ConfigManager setting : ConfigManager.values()) {
            setting.setValue("ShadowbaneSmokeSecret_" + setting.name());
        }
        if (!ConfigManager.init()) {
            throw new IllegalStateException("Complete configuration was rejected");
        }
        for (ConfigManager setting : ConfigManager.values()) {
            if (!("ShadowbaneSmokeSecret_" + setting.name()).equals(setting.getValue())) {
                throw new IllegalStateException("Configuration value was changed");
            }
        }
        ConfigManager.configMap.remove(ConfigManager.MB_DATABASE_PASS.name());
        if (ConfigManager.init()) {
            throw new IllegalStateException("Missing required configuration was accepted");
        }
        System.out.println("Credential logging smoke passed");
    }
}
