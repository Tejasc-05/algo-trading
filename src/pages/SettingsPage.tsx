import { Bell, CreditCard, Key, Shield, User } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { useAppStore } from '@/store/useAppStore'

export function SettingsPage() {
  const user = useAppStore((s) => s.user)

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-bold">Settings</h2>
        <p className="text-sm text-muted-foreground">Manage your account and platform preferences</p>
      </div>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile"><User className="h-4 w-4 mr-1" /> Profile</TabsTrigger>
          <TabsTrigger value="notifications"><Bell className="h-4 w-4 mr-1" /> Notifications</TabsTrigger>
          <TabsTrigger value="security"><Shield className="h-4 w-4 mr-1" /> Security</TabsTrigger>
          <TabsTrigger value="billing"><CreditCard className="h-4 w-4 mr-1" /> Billing</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Profile Information</CardTitle>
              <CardDescription>Update your personal details</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Full Name</Label>
                  <Input defaultValue={user.name} />
                </div>
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input defaultValue={user.email} type="email" />
                </div>
              </div>
              <Button variant="gradient" disabled title="Profile editing is not available yet">Save Changes</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Notification Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                { label: 'Trade Executions', desc: 'Notify when bots execute trades' },
                { label: 'Strategy Alerts', desc: 'Condition triggers and signals' },
                { label: 'Price Alerts', desc: 'Custom price level notifications' },
                { label: 'Weekly Reports', desc: 'Performance summary emails' },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between py-2">
                  <div>
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className="text-xs text-muted-foreground">{item.desc}</p>
                  </div>
                  <Switch disabled />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Key className="h-4 w-4" />
                Security Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Current Password</Label>
                  <Input type="password" />
                </div>
                <div className="space-y-2">
                  <Label>New Password</Label>
                  <Input type="password" />
                </div>
                <Button variant="outline" disabled>Update Password</Button>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Two-Factor Authentication</p>
                  <p className="text-xs text-muted-foreground">Add an extra layer of security</p>
                </div>
                <Button variant="outline" size="sm" disabled>Enable 2FA</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="billing">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Subscription Plan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-lg bg-primary/5 border border-primary/20">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">{user.plan.toUpperCase()} Plan</p>
                    <Badge>Current</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">Paper trading account</p>
                </div>
                <Button variant="outline" size="sm" disabled>Upgrade</Button>
              </div>
              <Separator />
              <p className="text-sm text-muted-foreground">No billing service is configured.</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
