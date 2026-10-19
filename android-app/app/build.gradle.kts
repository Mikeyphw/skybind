plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Never fall back to AGP's ephemeral hosted debug keystore. Production and
// test APKs must share the pinned, persistent key provisioned outside Git.
val stableKeyPath = providers.environmentVariable("SKYBIND_ANDROID_KEYSTORE_PATH").orNull
val stableKeyPassword = providers.environmentVariable("SKYBIND_ANDROID_KEYSTORE_PASSWORD").orNull
require(!stableKeyPath.isNullOrBlank() && !stableKeyPassword.isNullOrBlank()) {
    "Skybind hosted persistent signing credentials are required"
}
val stableKeyFile = file(stableKeyPath!!)
require(stableKeyFile.isFile) { "Skybind persistent signing keystore is absent" }

android {
    namespace = "io.github.mikeyphw.skybind"
    compileSdk = 35
    defaultConfig {
        applicationId = "io.github.mikeyphw.skybind"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-dev"
        testApplicationId = "io.github.mikeyphw.skybind.test"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    signingConfigs {
        create("skybindPersistentDebug") {
            storeFile = stableKeyFile
            storePassword = stableKeyPassword
            keyAlias = "skybind_dev"
            keyPassword = stableKeyPassword
            storeType = "pkcs12"
        }
    }
    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("skybindPersistentDebug") }
        getByName("release") { isMinifyEnabled = false }
    }
    buildFeatures { compose = true; buildConfig = true; aidl = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    testOptions { animationsDisabled = true }
}
dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.04.01")
    implementation(composeBom)
    implementation("com.github.topjohnwu.libsu:core:6.0.0")
    implementation("com.github.topjohnwu.libsu:service:6.0.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.4")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.foundation:foundation")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:core:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("junit:junit:4.13.2")
    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
