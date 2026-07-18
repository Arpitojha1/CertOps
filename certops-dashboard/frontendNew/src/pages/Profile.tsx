import { useState, useEffect } from "react"
import { User, Shield, Mail, Key } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { PromptModal } from "@/components/ui/prompt-modal"
import { apiGet, apiPut } from "@/lib/api"
import { useAppStore, UserProfile } from "@/lib/store"

export default function Profile() {
  const { user, setUser } = useAppStore()
  const [profile, setProfile] = useState<UserProfile | null>(user)
  const [email, setEmail] = useState(user?.email || "")
  const [isSavingProfile, setIsSavingProfile] = useState(false)

  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [isSavingPassword, setIsSavingPassword] = useState(false)
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string, status?: "info" | "warning" | "success"}>({isOpen: false})

  useEffect(() => {
    if (user) {
      setProfile(user)
      setEmail(user.email)
    } else {
      apiGet<UserProfile>("/auth/me")
        .then((p) => {
          setProfile(p)
          setEmail(p.email)
          setUser(p)
        })
        .catch(() => {/* use placeholder */})
    }
  }, [user, setUser])

  const handleSaveProfile = () => {
    setIsSavingProfile(true)
    apiPut<UserProfile>("/auth/me", { email })
      .then((updated) => {
        setProfile(updated)
        setUser(updated)
        setPrompt({ isOpen: true, title: "Profile Updated", desc: "Your email and profile details have been saved successfully.", status: "success" })
      })
      .catch((err: any) => {
        setPrompt({ isOpen: true, title: "Update Failed", desc: `Could not save profile: ${err?.response?.data?.detail || err.message || "Network error"}`, status: "warning" })
      })
      .finally(() => setIsSavingProfile(false))
  }

  const handleUpdatePassword = () => {
    if (!currentPassword || !newPassword) {
      setPrompt({ isOpen: true, title: "Missing Information", desc: "Please enter both your current password and your new password.", status: "warning" })
      return
    }
    setIsSavingPassword(true)
    apiPut("/auth/password", { current_password: currentPassword, new_password: newPassword })
      .then(() => {
        setPrompt({ isOpen: true, title: "Password Changed", desc: "Your password has been updated securely.", status: "success" })
        setCurrentPassword("")
        setNewPassword("")
      })
      .catch((err) => {
        setPrompt({ isOpen: true, title: "Password Change Failed", desc: `${err?.response?.data?.detail || err.message || "Invalid credentials"}`, status: "warning" })
      })
      .finally(() => setIsSavingPassword(false))
  }

  const initials = email ? email.slice(0, 2).toUpperCase() : "AD"
  const roleLabel = profile?.role === "admin" ? "Global Admin" : "Viewer"

  return (
    <div className="max-w-4xl mx-auto space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
        status={prompt.status}
      />

      <div>
        <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">My Profile</h1>
        <p className="text-neutral-500 font-medium">Manage your identity and personal settings</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <Card className="p-6 flex flex-col items-center text-center rounded-3xl">
            <div className="w-24 h-24 rounded-full bg-brand-purple flex items-center justify-center text-3xl font-bold text-brand-dark mb-4 shadow-inner">
              {initials}
            </div>
            <h2 className="text-xl font-bold mb-1">{profile ? profile.email.split("@")[0] : "Admin User"}</h2>
            <p className="text-neutral-500 text-sm mb-6">{profile?.role === "admin" ? "Administrator" : "Viewer"}</p>
            <Badge variant="outline" className="mb-6 rounded-full">{roleLabel}</Badge>
            <Button 
              variant="outline" 
              className="w-full rounded-full font-bold" 
              onClick={() => setPrompt({
                isOpen: true,
                title: "Upload Photo",
                desc: "Custom avatar image upload is not implemented yet. The avatar is generated from your email initials."
              })}
            >
              Upload Photo
            </Button>
          </Card>
        </div>

        <div className="md:col-span-2 space-y-6">
          <Card className="p-6 rounded-3xl">
            <h3 className="text-lg font-bold mb-4">Personal Information</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Email Address</label>
                <Input value={email} onChange={e => setEmail(e.target.value)} type="email" />
              </div>
              <div className="pt-2">
                <Button variant="lime" className="rounded-full font-bold shadow-sm" onClick={handleSaveProfile} disabled={isSavingProfile}>
                  {isSavingProfile ? "Saving…" : "Save Changes"}
                </Button>
              </div>
            </div>
          </Card>

          <Card className="p-6 rounded-3xl">
            <h3 className="text-lg font-bold mb-4">Security</h3>
            <div className="space-y-4">
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-neutral-700 mb-1">Current Password</label>
                  <Input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Enter current password" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-neutral-700 mb-1">New Password</label>
                  <Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Min 8 characters" />
                </div>
                <div>
                  <Button variant="outline" size="sm" className="rounded-full font-bold" onClick={handleUpdatePassword} disabled={isSavingPassword}>
                    {isSavingPassword ? "Updating…" : "Update Password"}
                  </Button>
                </div>
              </div>
              <div className="flex items-center justify-between p-4 bg-neutral-50 rounded-3xl">
                <div className="flex items-center gap-3">
                  <Shield className="w-5 h-5 text-brand-lime" />
                  <div>
                    <div className="font-semibold text-sm">Two-Factor Authentication</div>
                    <div className="text-xs text-neutral-500">Enabled via Authenticator App</div>
                  </div>
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="rounded-full font-bold"
                  onClick={() => setPrompt({
                    isOpen: true,
                    title: "Two-Factor Authentication",
                    desc: "2FA enrollment and device management settings are not implemented yet."
                  })}
                >
                  Manage
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
